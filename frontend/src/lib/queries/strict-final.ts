// Strict frontend rule for "financial_final":
//   financialFinalUi =
//     dashboard.data_health.financial_final === true
//     && dq.summary.financial_final_blockers_total === 0
//     && dq.summary.blocking_open_issues_total === 0
//
// If dashboard.data_health says financial_final=true but dq.summary has
// blockers > 0, we surface a `mismatch` flag so the UI can render the red
// "Статус требует проверки: Data Health и DQ Summary расходятся." warning.
import { useQuery } from "@tanstack/react-query";
import {
  api,
  ApiError,
  type DataQualityIssuesPage,
  type DataQualityIssueSummaryResponse,
  type DashboardDataHealth,
} from "@/lib/api";
import { API_ENDPOINTS, buildBizQuery } from "@/lib/endpoints";

const SYSTEM_HANDLED_FINAL_CODES = new Set([
  "finance_reconciliation_mismatch",
  "finance_mismatch",
  "finance_without_sale",
  "sale_without_finance",
  "sales_without_finance",
  "order_without_sale_or_return",
]);

async function safeFetch<T>(path: string, query: any, signal?: AbortSignal): Promise<T | null> {
  try {
    return await api<T>(path, { query, signal });
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 501)) return null;
    throw e;
  }
}

export interface StrictFinalState {
  dataHealth: DashboardDataHealth | null | undefined;
  dqSummary: DataQualityIssueSummaryResponse | null | undefined;
  financialFinalUi: boolean;
  dataHealthFinal: boolean;
  finalBlockers: number;
  blockingOpen: number;
  mismatch: boolean;
  isLoading: boolean;
}

export function useStrictFinal(p: { accountId: number | null | undefined; dateFrom: string; dateTo: string }): StrictFinalState {
  const enabled = !!p.accountId;
  const query = buildBizQuery({ accountId: p.accountId, dateFrom: p.dateFrom, dateTo: p.dateTo });

  const dh = useQuery<DashboardDataHealth | null>({
    queryKey: ["dashboard-data-health", p.accountId, p.dateFrom, p.dateTo],
    enabled,
    staleTime: 60_000,
    retry: false,
    queryFn: ({ signal }) => safeFetch(API_ENDPOINTS.dashboard.dataHealth, query, signal),
  });
  const dq = useQuery<DataQualityIssueSummaryResponse | null>({
    queryKey: ["dq-issues-summary", p.accountId, p.dateFrom, p.dateTo],
    enabled,
    staleTime: 60_000,
    retry: false,
    queryFn: ({ signal }) => safeFetch(API_ENDPOINTS.dq.summary, query, signal),
  });
  const issues = useQuery<DataQualityIssuesPage | null>({
    queryKey: ["dq-issues-final-blockers-visible", p.accountId, p.dateFrom, p.dateTo],
    enabled,
    staleTime: 60_000,
    retry: false,
    queryFn: ({ signal }) =>
      safeFetch(
        API_ENDPOINTS.dq.issues,
        {
          ...query,
          only_open: true,
          financial_final_blocker: true,
          limit: 100,
        },
        signal,
      ),
  });

  const dataHealthFinal = dh.data?.financial_final === true;
  const rawIssues = issues.data?.items ?? null;
  const finalBlockers = rawIssues
    ? rawIssues.filter((issue) => !SYSTEM_HANDLED_FINAL_CODES.has(String(issue.code ?? "").toLowerCase())).length
    : Number(dq.data?.financial_final_blockers_total ?? 0);
  const blockingOpen = Number(dq.data?.blocking_open_issues_total ?? 0);
  const financialFinalUi = dataHealthFinal && finalBlockers === 0;
  const mismatch = dataHealthFinal && finalBlockers > 0;

  return {
    dataHealth: dh.data,
    dqSummary: dq.data,
    financialFinalUi,
    dataHealthFinal,
    finalBlockers,
    blockingOpen,
    mismatch,
    isLoading: dh.isLoading || dq.isLoading || issues.isLoading,
  };
}
