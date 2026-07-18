// Global trust banner mounted on every authenticated page.
// Uses the shared /money/summary cache (see lib/queries/money-summary) so
// it does NOT trigger a second network call on pages that already fetch it.
// Strict rule: financial_final shown only if BOTH /dashboard/data-health
// and /dq/issues/summary agree there are no financial-final blockers.
import { useQuery } from "@tanstack/react-query";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";
import { moneySummaryQueryOptions } from "@/lib/queries/money-summary";
import {
  trustInputsFromSummary,
  type QualityInput,
  type TrustInput,
} from "@/components/money-ui/TrustStatusBanner";
import {
  api,
  type DashboardDataHealth,
  type DataQualityIssuesPage,
  type DataQualityIssueSummaryResponse,
} from "@/lib/api";
import { API_ENDPOINTS, buildBizQuery } from "@/lib/endpoints";
import { cn } from "@/lib/utils";
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";

const SYSTEM_HANDLED_FINAL_CODES = new Set([
  "finance_reconciliation_mismatch",
  "finance_mismatch",
  "finance_without_sale",
  "sale_without_finance",
  "sales_without_finance",
  "order_without_sale_or_return",
]);

type Tone = "success" | "warning" | "danger";

const TONE_CLASS: Record<Tone, string> = {
  success: "border-emerald-500/35 bg-emerald-500/10 text-emerald-800",
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-900",
  danger: "border-red-500/40 bg-red-500/10 text-red-700",
};

function pickHeadline(trust: TrustInput): { tone: Tone; text: string } {
  if (trust.business_status === "data_blocked") {
    return {
      tone: "danger",
      text: "Бизнес-рекомендации заблокированы. Сначала исправьте данные",
    };
  }
  if (trust.financial_final === true) {
    return { tone: "success", text: "Финальные данные подтверждены" };
  }
  return { tone: "warning", text: "Данные предварительные" };
}

function qualityNotices(
  quality: QualityInput,
): Array<{ tone: Tone; text: string }> {
  const notices: Array<{ tone: Tone; text: string }> = [];
  if (quality.supplier_confirmed_cost_coverage_percent === 0) {
    notices.push({
      tone: "warning",
      text: "Подтверждённая себестоимость не загружена",
    });
  }
  if (quality.ads_allocation_status === "overallocated") {
    notices.push({
      tone: "warning",
      text: "Реклама распределена с предупреждением",
    });
  }
  if ((quality.open_issues_total ?? 0) > 0) {
    notices.push({
      tone: "warning",
      text: `Открытых data issues: ${quality.open_issues_total}`,
    });
  }
  return notices;
}

function CompactNotice({
  tone,
  text,
  strong = false,
}: {
  tone: Tone;
  text: string;
  strong?: boolean;
}) {
  const Icon =
    tone === "success"
      ? CheckCircle2
      : tone === "danger"
        ? XCircle
        : AlertTriangle;
  return (
    <div
      className={cn(
        "inline-flex min-h-8 max-w-full shrink-0 items-center gap-2 rounded-lg border px-3 py-1.5 text-sm leading-tight shadow-sm shadow-black/[0.02]",
        TONE_CLASS[tone],
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className={cn("truncate", strong && "font-semibold")}>{text}</span>
    </div>
  );
}

export function GlobalWarningStrip() {
  const { activeId } = useAccounts();
  const { from, to } = useDateRange();

  const { data } = useQuery(
    moneySummaryQueryOptions({
      accountId: activeId,
      dateFrom: from,
      dateTo: to,
    }),
  );

  // Shared cache keys with the rest of the app (data-fix, costs, doctor, …)
  // so this strip does NOT trigger a second network call when those pages
  // are mounted. Keys must stay in sync with consumers in /data-fix and /costs.
  const { data: dqSummary } = useQuery<DataQualityIssueSummaryResponse>({
    queryKey: ["dq-issues-summary", activeId, from, to],
    enabled: !!activeId,
    staleTime: 60_000,
    queryFn: ({ signal }) =>
      api(API_ENDPOINTS.dq.summary, {
        query: buildBizQuery({
          accountId: activeId,
          dateFrom: from,
          dateTo: to,
        }),
        signal,
      }),
  });

  const { data: dataHealth } = useQuery<DashboardDataHealth>({
    queryKey: ["dashboard-data-health", activeId, from, to],
    enabled: !!activeId,
    staleTime: 60_000,
    queryFn: ({ signal }) =>
      api(API_ENDPOINTS.dashboard.dataHealth, {
        query: buildBizQuery({
          accountId: activeId,
          dateFrom: from,
          dateTo: to,
        }),
        signal,
      }),
  });

  const { data: finalIssues } = useQuery<DataQualityIssuesPage>({
    queryKey: ["dq-issues-final-blockers-visible", activeId, from, to],
    enabled: !!activeId,
    staleTime: 60_000,
    queryFn: ({ signal }) =>
      api(API_ENDPOINTS.dq.issues, {
        query: {
          ...buildBizQuery({ accountId: activeId, dateFrom: from, dateTo: to }),
          only_open: true,
          financial_final_blocker: true,
          limit: 100,
        },
        signal,
      }),
  });

  if (!data) return null;
  const inputs = trustInputsFromSummary(data);

  const rawFinalIssues = finalIssues?.items ?? null;
  const finalBlockers = rawFinalIssues
    ? rawFinalIssues.filter(
        (issue) =>
          !SYSTEM_HANDLED_FINAL_CODES.has(
            String(issue.code ?? "").toLowerCase(),
          ),
      ).length
    : Number(dqSummary?.financial_final_blockers_total ?? 0);
  const dataHealthFinal = dataHealth?.financial_final === true;

  // Strict UI rule
  const financialFinalUi = dataHealthFinal && finalBlockers === 0;

  const trust = { ...inputs.trust, financial_final: financialFinalUi };
  const showMismatch = dataHealthFinal && finalBlockers > 0;
  const headline = pickHeadline(trust);
  const notices = qualityNotices(inputs.quality);
  const label =
    trust.trust_label &&
    (trust.financial_final === true ||
      trust.trust_label !== "Доверенные данные")
      ? trust.trust_label
      : null;

  return (
    <div className="border-b border-border/60 bg-background/80 px-3 py-2 sm:px-5">
      <div className="flex items-center gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <CompactNotice tone={headline.tone} text={headline.text} strong />
        {label ? (
          <div className="inline-flex min-h-8 items-center rounded-lg border border-border/75 bg-card px-2.5 py-1 text-xs font-medium text-muted-foreground shadow-sm shadow-black/[0.015]">
            {label}
          </div>
        ) : null}
        {notices.map((notice) => (
          <CompactNotice
            key={notice.text}
            tone={notice.tone}
            text={notice.text}
          />
        ))}
        {finalBlockers > 0 && (
          <CompactNotice
            tone="warning"
            text={`Есть блокеры финальной сверки: ${finalBlockers}`}
          />
        )}
        {showMismatch && (
          <CompactNotice
            tone="danger"
            text="Статус требует проверки: Data Health и DQ Summary расходятся."
          />
        )}
      </div>
    </div>
  );
}
