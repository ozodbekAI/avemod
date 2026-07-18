// Shared TanStack Query options for /money/summary.
// Every consumer (GlobalWarningStrip, Dashboard, Money, Ads, …) MUST use
// this hook so we hit a single cache entry per (account, date-range) and
// the endpoint is only called once per page load.
import { queryOptions } from "@tanstack/react-query";
import { fetchMoneySummary } from "@/lib/money-endpoints";
import type { MMoneySummary } from "@/lib/api";

export const MONEY_SUMMARY_KEY = "money-summary" as const;

export function moneySummaryQueryOptions(params: {
  accountId: number | null | undefined;
  dateFrom: string;
  dateTo: string;
}) {
  const { accountId, dateFrom, dateTo } = params;
  return queryOptions<MMoneySummary>({
    // Canonical key — DO NOT introduce alternative keys for the same endpoint.
    queryKey: [MONEY_SUMMARY_KEY, accountId, dateFrom, dateTo],
    enabled: !!accountId,
    staleTime: 5 * 60 * 1000,
    queryFn: ({ signal }) =>
      fetchMoneySummary(
        { accountId: accountId as number, dateFrom, dateTo },
        signal,
      ) as Promise<MMoneySummary>,
  });
}
