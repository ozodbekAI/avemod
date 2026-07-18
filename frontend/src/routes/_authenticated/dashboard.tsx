/* eslint-disable @typescript-eslint/no-explicit-any */
// /dashboard — owner-first business overview.
// The page is intentionally dense and decision-oriented: money, trend, tasks,
// product/card risks and data trust from existing backend endpoints only.
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BarChart3,
  Boxes,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  CircleDollarSign,
  ClipboardCheck,
  CreditCard,
  DatabaseZap,
  Gauge,
  LineChart as LineChartIcon,
  ListChecks,
  PackageSearch,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";

import {
  api,
  type DashboardDataHealth,
  type MCardItem,
  type MDataBlockersResponse,
  type MMoneySummary,
  type Paginated,
} from "@/lib/api";
import { API_ENDPOINTS, buildBizQuery } from "@/lib/endpoints";
import {
  fetchBusinessDaily,
  fetchDataBlockers,
  fetchMoneyActionsToday,
  fetchMoneyArticles,
} from "@/lib/money-endpoints";
import { moneySummaryQueryOptions } from "@/lib/queries/money-summary";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";
import {
  formatDateTime,
  formatMoney,
  formatMoneyCompact,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import { cn } from "@/lib/utils";

import { PageHeader, PageShell } from "@/components/PageShell";
import { EndpointError } from "@/components/EndpointError";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/_authenticated/dashboard")({
  component: OwnerDashboardPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

type OwnerDashboard = {
  computed_at?: string | null;
  account_id: number;
  date_from: string;
  date_to: string;
  trust_state?: string | null;
  business_trusted?: boolean | null;
  operational_trusted?: boolean | null;
  financial_final?: boolean | null;
  can_generate_business_actions?: boolean | null;
  primary_message?: string | null;
  owner_message?: {
    status?: string | null;
    title?: string | null;
    reason?: string | null;
    today_focus?: string | null;
  } | null;
  trust?: {
    status?: string | null;
    trust_state?: string | null;
    financial_final?: boolean | null;
    operational_trusted?: boolean | null;
    business_trusted?: boolean | null;
    blocking_open_issues_total?: number | null;
    financial_final_blockers_total?: number | null;
    human_message?: string | null;
  } | null;
  revenue?: number | null;
  revenue_final?: number | null;
  net_profit?: number | null;
  net_profit_after_overhead?: number | null;
  net_profit_after_all_expenses?: number | null;
  margin_percent?: number | null;
  roi_percent?: number | null;
  ad_spend?: number | null;
  ad_spend_operational?: number | null;
  ad_spend_finance?: number | null;
  ad_spend_final?: number | null;
  ad_spend_source?: string | null;
  ad_spend_delta?: number | null;
  ads_source_spend?: number | null;
  stock_value?: number | null;
  overstock_value?: number | null;
  total_wb_expenses?: number | null;
  seller_cogs?: number | null;
  seller_other_expense?: number | null;
  total_seller_costs?: number | null;
  negative_profit_sku_count?: number | null;
  blocked_data_sku_count?: number | null;
  out_of_stock_risk_count?: number | null;
  action_summary?: Record<string, number | null | undefined> | null;
  top_risks?: OwnerItem[];
  top_opportunities?: OwnerItem[];
  next_actions_preview?: OwnerItem[];
  notes?: string[];
};

type OwnerItem = {
  id?: number | string | null;
  sku_id?: number | null;
  nm_id?: number | null;
  vendor_code?: string | null;
  title?: string | null;
  action_type?: string | null;
  priority?: string | null;
  confidence?: string | null;
  trust_state?: string | null;
  reason?: string | null;
  expected_effect_amount?: number | null;
  what_to_do?: string | null;
  why?: string | null;
  category?: string | null;
};

type OwnerAiSummary = {
  mode?: "ai" | "ai_fallback" | string;
  provider?: string | null;
  configured?: boolean | null;
  model?: string | null;
  title?: string | null;
  bullets?: string[];
  warnings?: string[];
  generated_at?: string | null;
};

type TrendPoint = {
  date: string;
  label: string;
  revenue: number;
  payout: number;
  expenses: number;
  ads: number;
  profit: number;
};

type ComparisonTrendPoint = TrendPoint & {
  previousDate?: string;
  previousLabel?: string;
  previousRevenue?: number;
  previousPayout?: number;
  previousProfit?: number;
  previousExpenses?: number;
  previousAds?: number;
};

type DateRangeValue = { from: string; to: string };

type MetricTone = "good" | "warning" | "danger" | "info" | "neutral";
type ComparisonValue = {
  label: string;
  tone: MetricTone;
  diff: number | null;
  percent: number | null;
};
type ExpenseBreakdownKey = "wb" | "seller";
type ExpenseBreakdownItem = {
  key: string;
  label: string;
  value: number;
  description?: string;
  final?: boolean | null;
};
type TrendMetricKey = "revenue" | "profit" | "expenses" | "ads" | "payout";
type TrendMetricConfig = {
  key: TrendMetricKey;
  label: string;
  currentLabel: string;
  previousLabel: string;
  color: string;
  inverse?: boolean;
};

const TREND_METRICS: TrendMetricConfig[] = [
  {
    key: "revenue",
    label: "Выручка",
    currentLabel: "Выручка текущего периода",
    previousLabel: "Выручка предыдущего периода",
    color: "var(--chart-5)",
  },
  {
    key: "profit",
    label: "Прибыль",
    currentLabel: "Прибыль текущего периода",
    previousLabel: "Прибыль предыдущего периода",
    color: "var(--chart-2)",
  },
  {
    key: "expenses",
    label: "Расходы",
    currentLabel: "Расходы текущего периода",
    previousLabel: "Расходы предыдущего периода",
    color: "var(--destructive)",
    inverse: true,
  },
  {
    key: "ads",
    label: "Реклама",
    currentLabel: "Реклама текущего периода",
    previousLabel: "Реклама предыдущего периода",
    color: "var(--warning)",
    inverse: true,
  },
  {
    key: "payout",
    label: "Выплаты",
    currentLabel: "Выплаты текущего периода",
    previousLabel: "Выплаты предыдущего периода",
    color: "var(--chart-4)",
  },
];

function OwnerDashboardPage() {
  const { activeId, loading: accountsLoading } = useAccounts();
  const { from, to, setRange, setPreset } = useDateRange();
  const previousRange = useMemo(() => previousPeriod({ from, to }), [from, to]);

  const params = activeId
    ? { accountId: activeId, dateFrom: from, dateTo: to }
    : null;
  const previousParams = activeId
    ? {
        accountId: activeId,
        dateFrom: previousRange.from,
        dateTo: previousRange.to,
      }
    : null;

  const summaryQ = useQuery(
    moneySummaryQueryOptions({
      accountId: activeId,
      dateFrom: from,
      dateTo: to,
    }),
  );
  const previousSummaryQ = useQuery(
    moneySummaryQueryOptions({
      accountId: activeId,
      dateFrom: previousRange.from,
      dateTo: previousRange.to,
    }),
  );

  const ownerQ = useQuery<OwnerDashboard | null>({
    queryKey: ["dashboard-owner", activeId, from, to],
    enabled: !!activeId,
    staleTime: 2 * 60 * 1000,
    queryFn: ({ signal }) =>
      api<OwnerDashboard>(API_ENDPOINTS.dashboard.owner, {
        query: buildBizQuery({
          accountId: activeId as number,
          dateFrom: from,
          dateTo: to,
        }),
        signal,
      }).catch(() => null),
  });

  const healthQ = useQuery<DashboardDataHealth | null>({
    queryKey: ["dashboard-data-health", activeId, from, to],
    enabled: !!activeId,
    staleTime: 2 * 60 * 1000,
    queryFn: ({ signal }) =>
      api<DashboardDataHealth>(API_ENDPOINTS.dashboard.dataHealth, {
        query: buildBizQuery({
          accountId: activeId as number,
          dateFrom: from,
          dateTo: to,
        }),
        signal,
      }).catch(() => null),
  });

  const actionsQ = useQuery<any>({
    queryKey: ["dashboard-actions-today", activeId, from, to],
    enabled: !!params,
    staleTime: 90_000,
    queryFn: () => fetchMoneyActionsToday({ ...params!, limit: 20 }),
  });

  const blockersQ = useQuery<MDataBlockersResponse | null>({
    queryKey: ["dashboard-data-blockers", activeId, from, to],
    enabled: !!params,
    staleTime: 90_000,
    queryFn: () => fetchDataBlockers(params!).catch(() => null),
  });

  const cardsQ = useQuery<Paginated<MCardItem> | MCardItem[] | null>({
    queryKey: ["dashboard-money-articles", activeId, from, to],
    enabled: !!params,
    staleTime: 2 * 60 * 1000,
    queryFn: () =>
      fetchMoneyArticles({ ...params!, limit: 8 }).catch(() => null) as Promise<
        Paginated<MCardItem> | MCardItem[] | null
      >,
    placeholderData: (prev) => prev,
  });

  const trendQ = useQuery<any>({
    queryKey: ["dashboard-money-trend", activeId, from, to],
    enabled: !!params,
    staleTime: 2 * 60 * 1000,
    queryFn: () =>
      fetchBusinessDaily({ ...params!, limit: 200 }).catch(() => null),
  });
  const previousTrendQ = useQuery<any>({
    queryKey: [
      "dashboard-money-trend",
      "previous",
      activeId,
      previousRange.from,
      previousRange.to,
    ],
    enabled: !!previousParams,
    staleTime: 2 * 60 * 1000,
    queryFn: () =>
      fetchBusinessDaily({ ...previousParams!, limit: 200 }).catch(() => null),
  });
  const ownerAiSummaryQ = useQuery<OwnerAiSummary | null>({
    queryKey: ["dashboard-owner-ai-summary", activeId, from, to],
    enabled: !!params,
    staleTime: 5 * 60 * 1000,
    retry: false,
    queryFn: ({ signal }) =>
      api<OwnerAiSummary>(API_ENDPOINTS.dashboard.ownerAiSummary, {
        query: buildBizQuery(params!),
        signal,
      }).catch(() => null),
  });

  const owner = ownerQ.data ?? undefined;
  const summary = summaryQ.data;
  const previousSummary = previousSummaryQ.data;
  const health = healthQ.data ?? undefined;
  const actions = useMemo(
    () => extractActions(actionsQ.data, owner, summary),
    [actionsQ.data, owner, summary],
  );
  const blockers = useMemo(
    () => extractBlockers(blockersQ.data),
    [blockersQ.data],
  );
  const cards = useMemo(
    () => extractCards(cardsQ.data, summary),
    [cardsQ.data, summary],
  );
  const trend = useMemo(() => buildTrendPoints(trendQ.data), [trendQ.data]);
  const previousTrend = useMemo(
    () => buildTrendPoints(previousTrendQ.data),
    [previousTrendQ.data],
  );
  const model = useMemo(
    () =>
      buildOwnerModel({
        owner,
        summary,
        health,
        actions,
        blockers,
        cards,
        trend,
        selectedRange: { from, to },
      }),
    [owner, summary, health, actions, blockers, cards, trend, from, to],
  );
  const previousModel = useMemo(
    () =>
      buildOwnerModel({
        summary: previousSummary,
        actions: [],
        blockers: [],
        cards: [],
        trend: previousTrend,
        selectedRange: previousRange,
      }),
    [previousSummary, previousTrend, previousRange],
  );

  if (!accountsLoading && !activeId) {
    return (
      <PageShell>
        <PageHeader
          title="Панель владельца"
          description="Выберите компанию, чтобы увидеть деньги, задачи и состояние карточек."
        />
        <NoAccountSelected />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="Панель владельца"
        description={`${formatRange(from, to)} · сравнение с ${formatRange(
          previousRange.from,
          previousRange.to,
        )}`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link to={"/money" as any}>
                <Wallet className="h-3.5 w-3.5" />
                Деньги
              </Link>
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link to={"/action-center" as any}>
                <ListChecks className="h-3.5 w-3.5" />
                Задачи
              </Link>
            </Button>
            <Button asChild size="sm">
              <Link to={"/products" as any}>
                <PackageSearch className="h-3.5 w-3.5" />
                Товары
              </Link>
            </Button>
          </div>
        }
      />

      <div className="space-y-5">
        <PeriodControls
          from={from}
          to={to}
          previousRange={previousRange}
          setRange={setRange}
          setPreset={setPreset}
        />

        <PeriodAuditPanel
          model={model}
          previousRange={previousRange}
          loading={summaryQ.isLoading && !summary}
        />

        <OwnerStatusHero
          loading={accountsLoading || (summaryQ.isLoading && ownerQ.isLoading)}
          model={model}
          summary={summary}
          owner={owner}
          health={health}
        />

        <MetricGrid
          loading={summaryQ.isLoading && !summary}
          model={model}
          previousModel={previousModel}
        />

        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(380px,0.85fr)]">
          <div className="space-y-5">
            <MoneyTrendCard
              loading={trendQ.isLoading || previousTrendQ.isLoading}
              trend={trend}
              previousTrend={previousTrend}
              model={model}
              previousModel={previousModel}
              summary={summary}
              range={{ from, to }}
              previousRange={previousRange}
            />
            <TasksCard
              loading={actionsQ.isLoading}
              actions={actions}
              model={model}
            />
            <DataTrustPanel
              loading={healthQ.isLoading && !health}
              health={health}
              blockers={blockers}
              model={model}
            />
          </div>

          <div className="space-y-5">
            <MoneyNowCard
              loading={summaryQ.isLoading && !summary}
              model={model}
              previousModel={previousModel}
              summary={summary}
            />
            <CardsHealthCard
              loading={cardsQ.isLoading && !cards.length}
              cards={cards}
              model={model}
            />
            <OwnerNotesPanel
              owner={owner}
              summary={summary}
              model={model}
              aiSummary={ownerAiSummaryQ.data ?? undefined}
              aiLoading={ownerAiSummaryQ.isLoading}
            />
          </div>
        </div>
      </div>
    </PageShell>
  );
}

function PeriodControls({
  from,
  to,
  previousRange,
  setRange,
  setPreset,
}: {
  from: string;
  to: string;
  previousRange: DateRangeValue;
  setRange: (from: string, to: string) => void;
  setPreset: (days: number) => void;
}) {
  const days = daysInclusive({ from, to });
  const activePreset = days === 7 ? "week" : days === 30 ? "month" : "custom";

  return (
    <Card className="rounded-lg shadow-sm">
      <CardContent className="p-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="mr-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <CalendarDays className="h-3.5 w-3.5" />
              Период
            </div>
            <Button
              size="sm"
              variant={activePreset === "week" ? "default" : "outline"}
              onClick={() => setPreset(7)}
            >
              Неделя
            </Button>
            <Button
              size="sm"
              variant={activePreset === "month" ? "default" : "outline"}
              onClick={() => setPreset(30)}
            >
              Месяц
            </Button>
            <Button
              size="sm"
              variant={activePreset === "custom" ? "default" : "outline"}
              onClick={() => setRange(from, to)}
            >
              Произвольный период
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Input
              type="date"
              value={from}
              onChange={(event) => setRange(event.target.value, to)}
              className="h-8 w-[150px]"
              aria-label="Дата начала периода"
            />
            <Input
              type="date"
              value={to}
              onChange={(event) => setRange(from, event.target.value)}
              className="h-8 w-[150px]"
              aria-label="Дата окончания периода"
            />
            <Badge variant="outline" className="rounded-md">
              {days} дн.
            </Badge>
          </div>
        </div>
        <div className="mt-2 text-xs text-muted-foreground">
          Сравнение строится с предыдущим равным периодом:{" "}
          <span className="font-medium text-foreground">
            {formatRange(previousRange.from, previousRange.to)}
          </span>
          .
        </div>
      </CardContent>
    </Card>
  );
}

function PeriodAuditPanel({
  model,
  previousRange,
  loading,
}: {
  model: ReturnType<typeof buildOwnerModel>;
  previousRange: DateRangeValue;
  loading: boolean;
}) {
  const hasMismatch =
    !model.hasMoneySummary ||
    !model.hasOwnerData ||
    model.summaryPeriodMismatch ||
    model.ownerPeriodMismatch;
  const items = [
    {
      icon: CalendarDays,
      label: "Выбранный период",
      value: model.selectedPeriodLabel,
      tone: "info" as MetricTone,
    },
    {
      icon: CircleDollarSign,
      label: "Сводка денег",
      value: model.hasMoneySummary
        ? (model.summaryPeriodLabel ?? model.selectedPeriodLabel)
        : "нет данных",
      tone:
        !model.hasMoneySummary || model.summaryPeriodMismatch
          ? "warning"
          : ("good" as MetricTone),
    },
    {
      icon: Gauge,
      label: "Панель владельца",
      value: model.hasOwnerData
        ? (model.ownerPeriodLabel ?? "по запросу")
        : "нет данных",
      tone:
        !model.hasOwnerData || model.ownerPeriodMismatch
          ? "warning"
          : ("neutral" as MetricTone),
    },
    {
      icon: BadgeCheck,
      label: "Период сравнения",
      value: formatRange(previousRange.from, previousRange.to),
      tone: "neutral" as MetricTone,
    },
  ];

  return (
    <Card className="rounded-lg border bg-card shadow-sm">
      <CardContent className="p-3">
        {loading ? (
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-16 rounded-md" />
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold">
                  {hasMismatch ? (
                    <AlertTriangle className="h-4 w-4 text-warning" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4 text-success" />
                  )}
                  Контроль периода и источника
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Денежные показатели берутся из сводки денег за выбранный
                  период; данные панели владельца используются только как
                  резерв.
                </div>
              </div>
              {model.financeClosedPeriodLabel ? (
                <Badge variant="outline" className="rounded-md">
                  WB закрыт: {model.financeClosedPeriodLabel}
                </Badge>
              ) : null}
            </div>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {items.map((item) => {
                const Icon = item.icon;
                const cls = toneClasses(item.tone);
                return (
                  <div
                    key={item.label}
                    className={cn(
                      "flex min-w-0 items-center gap-2 rounded-md border px-3 py-2",
                      cls.soft,
                    )}
                  >
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-background/70">
                      <Icon className="h-4 w-4" />
                    </span>
                    <div className="min-w-0">
                      <div className="truncate text-[11px] text-muted-foreground">
                        {item.label}
                      </div>
                      <div className="truncate text-sm font-semibold tabular-nums">
                        {item.value}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            {hasMismatch ? (
              <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs leading-5 text-warning">
                Источник или период требует внимания. Для главных денежных
                карточек используется единая сводка денег, чтобы показатели
                панели владельца и финансового кабинета не спорили между собой.
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function buildOwnerModel(input: {
  owner?: OwnerDashboard;
  summary?: MMoneySummary;
  health?: DashboardDataHealth;
  actions: OwnerItem[];
  blockers: any[];
  cards: any[];
  trend: TrendPoint[];
  selectedRange?: DateRangeValue;
}) {
  const {
    owner,
    summary,
    health,
    actions,
    blockers,
    cards,
    trend,
    selectedRange,
  } = input;
  const k = summary?.kpis as any;
  const meta = (summary?.meta ?? {}) as any;
  const fr = ((summary as any)?.finance_reconciliation ?? {}) as any;
  const trust = (summary?.trust ?? (summary?.meta as any)?.data_trust) as any;
  const ownerTrust = owner?.trust;

  const revenue = num(
    fr.operational_revenue,
    k?.finance_reconciliation_operational_revenue,
    k?.revenue_final,
    k?.revenue,
    owner?.revenue_final,
    owner?.revenue,
  );
  const financeConfirmedRevenue = num(
    fr.finance_confirmed_revenue,
    k?.finance_confirmed_revenue,
  );
  const reconciliationDifference = num(
    fr.difference_amount,
    k?.finance_difference_amount,
  );
  const reconciliationDifferencePercent = num(
    fr.difference_percent,
    k?.finance_difference_percent,
  );
  const reconciliationStatus = String(
    fr.status ?? k?.finance_reconciliation_status ?? "not_available",
  );
  const profitFinanceBasis = num(
    k?.net_profit_after_all_expenses,
    owner?.net_profit_after_all_expenses,
  );
  const profit = num(
    k?.net_profit_after_all_expenses,
    k?.net_profit_after_overhead,
    k?.profit_after_source_ads,
    k?.net_profit_after_ads,
    owner?.net_profit_after_all_expenses,
    owner?.net_profit_after_overhead,
    owner?.net_profit,
  );
  const margin = num(
    k?.margin_after_overhead_percent,
    k?.margin_percent,
    owner?.margin_percent,
  );
  const roi = num(k?.roi_on_cogs_percent, k?.roi_percent, owner?.roi_percent);
  const cash = num(
    k?.cash_on_wb_current,
    k?.cash_on_wb,
    k?.available_for_withdraw,
  );
  const withdraw = num(
    k?.available_for_withdraw_current,
    k?.available_for_withdraw,
  );
  const adSpendFinance = num(
    k?.ad_spend_finance,
    k?.ad_spend_final,
    owner?.ad_spend_finance,
    owner?.ad_spend_final,
  );
  const adSpendFinal = num(
    k?.ad_spend_final,
    k?.ad_spend,
    owner?.ad_spend_final,
    owner?.ad_spend,
  );
  const adSpendOperationalRaw = num(
    k?.ad_spend_operational,
    owner?.ad_spend_operational,
  );
  const adSpendSource = num(
    k?.ads_source_spend,
    k?.ads_allocated_spend,
    owner?.ads_source_spend,
  );
  const adSpendOperational =
    firstPositive(adSpendOperationalRaw, adSpendSource) ??
    adSpendOperationalRaw ??
    adSpendSource;
  const adSpend = adSpendFinal ?? adSpendOperational;
  const stockValue = num(k?.stock_value, owner?.stock_value);
  const overstock = num(k?.overstock_value, owner?.overstock_value);
  const expenses = num(
    k?.wb_expenses_total,
    k?.direct_wb_expenses,
    owner?.total_wb_expenses,
  );
  const cogs = num(k?.seller_cogs, owner?.seller_cogs);
  const sellerOtherExpense = num(
    k?.seller_other_expense,
    owner?.seller_other_expense,
  );
  const totalSellerCosts = num(
    k?.total_seller_expenses,
    k?.total_seller_costs,
    owner?.total_seller_costs,
  );
  const negativeSku = intNum(
    k?.negative_profit_sku_count,
    owner?.negative_profit_sku_count,
  );
  const dataBlockedSku = intNum(
    k?.blocked_data_sku_count,
    owner?.blocked_data_sku_count,
  );
  const stockRisk = intNum(
    owner?.out_of_stock_risk_count,
    cardSummaryNum(cards, "stock_risk_count"),
  );

  const actionSummary =
    owner?.action_summary ?? (actions as any)?.summary ?? {};
  const criticalActions = intNum(
    actionSummary?.critical,
    countByPriority(actions, "critical"),
  );
  const highActions = intNum(
    actionSummary?.high,
    countByPriority(actions, "high"),
  );
  const dataFixActions = intNum(
    actionSummary?.data_blocked_count,
    actionSummary?.data_fix,
    actionSummary?.data_fix_actions_count,
  );
  const urgentActions = actions.filter((a) =>
    ["critical", "high"].includes(String(a.priority ?? "").toLowerCase()),
  ).length;
  const blockerCount = intNum(
    ownerTrust?.blocking_open_issues_total,
    owner?.blocking_open_issues_total,
    (summary?.trust as any)?.blocking_open_issues_total,
    (blockers as any)?.length,
  );
  const finalBlockers = intNum(
    ownerTrust?.financial_final_blockers_total,
    owner?.financial_final_blockers_total,
    health?.financial_final_blockers_total,
    (summary?.trust as any)?.financial_final_blockers_total,
  );
  const openIssues = intNum(health?.open_issues_total, blockerCount);
  const costCoverage = num(
    health?.revenue_cost_coverage_percent,
    health?.sku_cost_coverage_percent,
    k?.business_cost_coverage_percent,
    k?.supplier_cost_confirmed_revenue_percent,
  );
  const financialFinal = Boolean(
    owner?.financial_final ??
    ownerTrust?.financial_final ??
    trust?.financial_final,
  );
  const operationalTrusted = Boolean(
    owner?.operational_trusted ??
    ownerTrust?.operational_trusted ??
    trust?.operational_trusted,
  );
  const trustState = String(
    owner?.trust_state ||
      ownerTrust?.trust_state ||
      trust?.trust_state ||
      trust?.state ||
      "unknown",
  );
  const canAct = Boolean(
    owner?.can_generate_business_actions ??
    trust?.can_generate_business_actions ??
    actions.length > 0,
  );

  const status = deriveOwnerStatus({
    financialFinal,
    operationalTrusted,
    urgentActions,
    blockerCount,
    finalBlockers,
    profit,
    dataBlockedSku,
    negativeSku,
    hasData: Boolean(summary || owner),
  });

  const totalRiskSku = negativeSku + dataBlockedSku + stockRisk;
  const riskMoney =
    sum(actions.map((a) => num(a.expected_effect_amount))) ||
    sumRiskAmount(summary);
  const profitTone: MetricTone =
    profit == null
      ? "neutral"
      : profit < 0
        ? "danger"
        : margin != null && margin < 8
          ? "warning"
          : "good";
  const trendProfit = trend.length
    ? (trend[trend.length - 1]?.profit ?? null)
    : null;
  const summaryPeriod = periodFromObject(meta, summary as any);
  const ownerPeriod = periodFromObject(owner);
  const selectedPeriodLabel = selectedRange
    ? formatRange(selectedRange.from, selectedRange.to)
    : "—";
  const summaryPeriodLabel = summaryPeriod
    ? formatRange(summaryPeriod.from, summaryPeriod.to)
    : null;
  const ownerPeriodLabel = ownerPeriod
    ? formatRange(ownerPeriod.from, ownerPeriod.to)
    : null;
  const summaryPeriodMismatch = Boolean(
    selectedRange &&
    summaryPeriod &&
    (summaryPeriod.from !== selectedRange.from ||
      summaryPeriod.to !== selectedRange.to),
  );
  const ownerPeriodMismatch = Boolean(
    selectedRange &&
    ownerPeriod &&
    (ownerPeriod.from !== selectedRange.from ||
      ownerPeriod.to !== selectedRange.to),
  );
  const financeClosedPeriodLabel =
    text(fr.closed_finance_period_label) ||
    (fr.closed_finance_date_from && fr.closed_finance_date_to
      ? formatRange(fr.closed_finance_date_from, fr.closed_finance_date_to)
      : fr.closed_finance_date_to
        ? formatShortDate(fr.closed_finance_date_to)
        : null);

  return {
    selectedPeriodLabel,
    hasMoneySummary: Boolean(summary),
    hasOwnerData: Boolean(owner),
    summaryPeriodLabel,
    ownerPeriodLabel,
    summaryPeriodMismatch,
    ownerPeriodMismatch,
    financeClosedPeriodLabel,
    financeConfirmedRevenue,
    reconciliationDifference,
    reconciliationDifferencePercent,
    reconciliationStatus,
    revenue,
    profit,
    profitFinanceBasis,
    margin,
    roi,
    cash,
    withdraw,
    adSpend,
    adSpendOperational,
    adSpendFinance,
    adSpendFinal,
    stockValue,
    overstock,
    expenses,
    cogs,
    sellerOtherExpense,
    totalSellerCosts,
    negativeSku,
    dataBlockedSku,
    stockRisk,
    totalRiskSku,
    criticalActions,
    highActions,
    dataFixActions,
    urgentActions,
    blockerCount,
    finalBlockers,
    openIssues,
    costCoverage,
    financialFinal,
    operationalTrusted,
    trustState,
    canAct,
    riskMoney,
    status,
    profitTone,
    trendProfit,
    ownerTitle: text(
      owner?.owner_message?.title,
      owner?.primary_message,
      summary?.answer?.title,
      status.title,
    ),
    ownerReason: text(
      owner?.owner_message?.reason,
      summary?.answer?.short_text,
      status.description,
    ),
    todayFocus: text(
      owner?.owner_message?.today_focus,
      actions[0]?.what_to_do,
      actions[0]?.reason,
      actions[0]?.title,
    ),
    updatedAt:
      owner?.computed_at ??
      summary?.computed_at ??
      summary?.meta?.generated_at ??
      null,
  };
}

function deriveOwnerStatus(input: {
  financialFinal: boolean;
  operationalTrusted: boolean;
  urgentActions: number;
  blockerCount: number;
  finalBlockers: number;
  profit: number | null;
  dataBlockedSku: number;
  negativeSku: number;
  hasData: boolean;
}) {
  if (!input.hasData) {
    return {
      tone: "info" as MetricTone,
      label: "Нужны данные",
      title: "Недостаточно данных для оценки бизнеса",
      description:
        "После подключения WB и завершения синхронизации здесь появится управленческий сигнал.",
      icon: DatabaseZap,
    };
  }
  if (input.blockerCount > 0 || input.finalBlockers > 0) {
    return {
      tone: "danger" as MetricTone,
      label: "Есть блокеры",
      title: "Сначала закройте блокеры данных",
      description:
        "Прибыль и риски пока не финальные. После закрытия блокеров расчёты станут пригодны для решений.",
      icon: ShieldAlert,
    };
  }
  if (input.profit != null && input.profit < 0) {
    return {
      tone: "danger" as MetricTone,
      label: "Убыток",
      title: "Бизнес в минусе, нужно защитить прибыль",
      description:
        "Проверьте убыточные SKU, рекламу и расходы WB. Самые важные действия уже отсортированы ниже.",
      icon: TrendingDown,
    };
  }
  if (
    input.urgentActions > 0 ||
    input.dataBlockedSku > 0 ||
    input.negativeSku > 0
  ) {
    return {
      tone: "warning" as MetricTone,
      label: "Нужна проверка",
      title: "Бизнес работает, но есть риски",
      description:
        "Для владельца ниже показаны задачи с максимальным влиянием на деньги и товары.",
      icon: AlertTriangle,
    };
  }
  if (input.financialFinal || input.operationalTrusted) {
    return {
      tone: "good" as MetricTone,
      label: "Под контролем",
      title: "Бизнес под контролем",
      description:
        "Критических сигналов нет. Можно смотреть результаты и возможности роста по карточкам.",
      icon: CheckCircle2,
    };
  }
  return {
    tone: "neutral" as MetricTone,
    label: "Проверяется",
    title: "Расчёты пока предварительные",
    description:
      "После синхронизации и пересчёта появятся точные сигналы для владельца.",
    icon: RefreshCw,
  };
}

function OwnerStatusHero({
  loading,
  model,
  summary,
  owner,
  health,
}: {
  loading: boolean;
  model: ReturnType<typeof buildOwnerModel>;
  summary?: MMoneySummary;
  owner?: OwnerDashboard;
  health?: DashboardDataHealth;
}) {
  if (loading) {
    return (
      <Card className="rounded-lg shadow-sm">
        <CardContent className="p-5">
          <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
            <div className="space-y-3">
              <Skeleton className="h-5 w-44" />
              <Skeleton className="h-8 w-3/4" />
              <Skeleton className="h-4 w-2/3" />
            </div>
            <Skeleton className="h-28 w-full" />
          </div>
        </CardContent>
      </Card>
    );
  }

  const StatusIcon = model.status.icon;
  const statusClass = toneClasses(model.status.tone);
  const finality = model.financialFinal
    ? "Прибыль финальная"
    : model.operationalTrusted
      ? "Операционные данные"
      : "Предварительный расчёт";

  return (
    <Card className={cn("rounded-lg shadow-sm border-l-4", statusClass.border)}>
      <CardContent className="p-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px] xl:items-center">
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                className={cn(
                  "rounded-md border px-2.5 py-1",
                  statusClass.badge,
                )}
              >
                <StatusIcon className="h-3.5 w-3.5" />
                {model.status.label}
              </Badge>
              <Badge variant="outline" className="rounded-md">
                {finality}
              </Badge>
              <Badge variant="outline" className="rounded-md">
                {trustLabel(model.trustState)}
              </Badge>
              {model.updatedAt ? (
                <span className="text-xs text-muted-foreground">
                  Обновлено: {formatDateTime(model.updatedAt)}
                </span>
              ) : null}
            </div>
            <div>
              <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                {model.ownerTitle}
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                {model.ownerReason}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button asChild>
                <Link to={"/action-center" as any}>
                  Открыть главную задачу
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link to={"/money" as any}>
                  Открыть отчёт по деньгам
                  <CircleDollarSign className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </div>
          </div>

          <div className="rounded-lg border bg-muted/30 p-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              Фокус владельца
            </div>
            <p className="mt-2 text-sm font-medium leading-6">
              {model.todayFocus ||
                "Обязательных действий сейчас нет. Следите за трендом денег и состоянием карточек."}
            </p>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <MiniStat
                label="Срочно"
                value={model.urgentActions}
                tone={model.urgentActions ? "danger" : "good"}
              />
              <MiniStat
                label="Блокеры"
                value={model.blockerCount}
                tone={model.blockerCount ? "danger" : "good"}
              />
              <MiniStat
                label="SKU в риске"
                value={model.totalRiskSku}
                tone={model.totalRiskSku ? "warning" : "good"}
              />
            </div>
          </div>
        </div>
        {!summary && !owner && !health ? (
          <div className="mt-4 rounded-md border border-dashed p-3 text-xs text-muted-foreground">
            Данные панели владельца ещё не пришли с сервера. Проверьте
            синхронизацию или настройки подключения.
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function MetricGrid({
  loading,
  model,
  previousModel,
}: {
  loading: boolean;
  model: ReturnType<typeof buildOwnerModel>;
  previousModel: ReturnType<typeof buildOwnerModel>;
}) {
  const adSpendDrr =
    model.revenue && model.adSpend != null && model.revenue > 0
      ? `DRR ${((model.adSpend / model.revenue) * 100).toFixed(1)}%`
      : null;
  const adFinanceNote =
    model.adSpend != null &&
    model.adSpendFinance != null &&
    Math.abs(model.adSpend - model.adSpendFinance) > 1
      ? `финансы WB: ${formatMoneyCompact(model.adSpendFinance)}`
      : null;
  const profitFinanceNote =
    model.profit != null &&
    model.profitFinanceBasis != null &&
    Math.abs(model.profit - model.profitFinanceBasis) > 1
      ? `финансы WB: ${formatMoneyCompact(model.profitFinanceBasis)}`
      : null;
  const revenueFinanceNote =
    model.financeConfirmedRevenue != null
      ? `WB подтверждено: ${formatMoneyCompact(model.financeConfirmedRevenue)}`
      : null;
  const metrics = [
    {
      title: "Выручка",
      value: money(model.revenue),
      previousValue: previousModel.revenue,
      comparison: compareValue(model.revenue, previousModel.revenue),
      sub: revenueFinanceNote ?? "Операционная выручка за выбранный период",
      icon: TrendingUp,
      tone: "info" as MetricTone,
      to: "/money",
    },
    {
      title: "Чистая прибыль",
      value: money(model.profit),
      previousValue: previousModel.profit,
      comparison: compareValue(model.profit, previousModel.profit),
      sub:
        [
          model.margin != null ? `Маржа ${formatPercent(model.margin)}` : null,
          profitFinanceNote,
        ]
          .filter(Boolean)
          .join(" · ") || "После WB, рекламы и расходов продавца",
      icon: Wallet,
      tone: model.profitTone,
      to: "/money",
    },
    {
      title: "Баланс WB",
      value: money(model.cash),
      previousValue: previousModel.cash,
      comparison: compareValue(model.cash, previousModel.cash),
      sub:
        model.withdraw != null
          ? `Доступно к выводу: ${formatMoneyCompact(model.withdraw)}`
          : "Последний снимок баланса",
      icon: CreditCard,
      tone: "good" as MetricTone,
      to: "/finance",
    },
    {
      title: "Деньги в риске",
      value:
        model.riskMoney > 0
          ? formatMoneyCompact(model.riskMoney)
          : model.totalRiskSku
            ? `${model.totalRiskSku} SKU`
            : "Нет",
      previousValue: previousModel.riskMoney,
      comparison: compareValue(model.riskMoney, previousModel.riskMoney, true),
      sub: model.totalRiskSku
        ? "Убыточные, без данных или риск остатков"
        : "Критических рисков нет",
      icon: ShieldAlert,
      tone: model.totalRiskSku ? "warning" : "good",
      to: "/action-center",
    },
    {
      title: "Расходы на рекламу",
      value: money(model.adSpend),
      previousValue: previousModel.adSpend,
      comparison: compareValue(model.adSpend, previousModel.adSpend, true),
      sub:
        [adSpendDrr, adFinanceNote].filter(Boolean).join(" · ") ||
        "Реклама за выбранный период",
      icon: BarChart3,
      tone:
        model.adSpend && model.revenue && model.adSpend / model.revenue > 0.2
          ? "warning"
          : "neutral",
      to: "/ads",
    },
    {
      title: "Деньги в остатках",
      value: money(model.stockValue),
      previousValue: previousModel.stockValue,
      comparison: compareValue(model.stockValue, previousModel.stockValue),
      sub:
        model.overstock != null && model.overstock > 0
          ? `Заморожено: ${formatMoneyCompact(model.overstock)}`
          : "Стоимость склада",
      icon: Boxes,
      tone: model.overstock && model.overstock > 0 ? "warning" : "neutral",
      to: "/stock-control",
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
      {metrics.map((metric) => (
        <MetricTile key={metric.title} loading={loading} {...metric} />
      ))}
    </div>
  );
}

function MetricTile({
  title,
  value,
  sub,
  icon: Icon,
  tone,
  to,
  loading,
  previousValue,
  comparison,
}: {
  title: string;
  value: string;
  sub: string;
  icon: typeof Wallet;
  tone: MetricTone;
  to: string;
  loading: boolean;
  previousValue?: number | null;
  comparison?: ComparisonValue;
}) {
  const cls = toneClasses(tone);
  return (
    <Card className="rounded-lg shadow-sm">
      <CardContent className="p-4">
        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-7 w-28" />
            <Skeleton className="h-3 w-32" />
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground">
                {title}
              </span>
              <span
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-md border",
                  cls.soft,
                )}
              >
                <Icon className="h-3.5 w-3.5" />
              </span>
            </div>
            <div>
              <div className="truncate text-2xl font-semibold tabular-nums tracking-tight">
                {value}
              </div>
              <div className="mt-1 truncate text-xs text-muted-foreground">
                {sub}
              </div>
              {comparison ? (
                <MetricComparisonBlock
                  comparison={comparison}
                  previousValue={previousValue}
                />
              ) : null}
            </div>
            <Button
              asChild
              variant="ghost"
              size="sm"
              className="h-7 px-0 text-xs"
            >
              <Link to={to as any}>
                Открыть
                <ArrowRight className="h-3 w-3" />
              </Link>
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MoneyTrendCard({
  loading,
  trend,
  previousTrend,
  model,
  previousModel,
  summary,
  range,
  previousRange,
}: {
  loading: boolean;
  trend: TrendPoint[];
  previousTrend: TrendPoint[];
  model: ReturnType<typeof buildOwnerModel>;
  previousModel: ReturnType<typeof buildOwnerModel>;
  summary?: MMoneySummary;
  range: DateRangeValue;
  previousRange: DateRangeValue;
}) {
  const [metricKey, setMetricKey] = useState<TrendMetricKey>("revenue");
  const metric =
    TREND_METRICS.find((item) => item.key === metricKey) ?? TREND_METRICS[0];
  const chartData = buildComparisonTrend(trend, previousTrend);
  const hasTrend = chartData.length > 1;
  const lastPoint = trend[trend.length - 1];
  const currentMetricTotal = sumTrendMetric(trend, metric.key);
  const previousMetricTotal = sumTrendMetric(previousTrend, metric.key);
  const metricComparison = compareValue(
    currentMetricTotal,
    previousMetricTotal,
    metric.inverse,
  );
  const previousDataKey = previousTrendDataKey(metric.key);

  return (
    <Card className="rounded-lg shadow-sm">
      <CardHeader className="space-y-3 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <LineChartIcon className="h-4 w-4 text-primary" />
              Денежный тренд
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              Текущий период против предыдущего:{" "}
              {formatRange(range.from, range.to)} vs{" "}
              {formatRange(previousRange.from, previousRange.to)}
            </p>
          </div>
          <Badge variant="outline" className="shrink-0 rounded-md">
            {hasTrend ? `${chartData.length} дн.` : "Дневные данные"}
          </Badge>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {TREND_METRICS.map((item) => (
            <Button
              key={item.key}
              type="button"
              size="sm"
              variant={item.key === metric.key ? "default" : "outline"}
              className="h-7 px-2 text-xs"
              onClick={() => setMetricKey(item.key)}
            >
              {item.label}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <Skeleton className="h-[310px] w-full" />
        ) : hasTrend ? (
          <div className="h-[310px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={chartData}
                margin={{ left: 4, right: 10, top: 10, bottom: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--border)"
                  opacity={0.55}
                />
                <XAxis
                  dataKey="label"
                  tickLine={false}
                  axisLine={false}
                  minTickGap={24}
                  tick={{ fontSize: 11 }}
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => compactAxis(v)}
                  width={48}
                />
                <RechartsTooltip content={<TrendTooltip />} />
                <Line
                  type="monotone"
                  dataKey={metric.key}
                  name={metric.currentLabel}
                  stroke={metric.color}
                  strokeWidth={2.4}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey={previousDataKey}
                  name={metric.previousLabel}
                  stroke={metric.color}
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="flex h-[310px] flex-col items-center justify-center rounded-lg border border-dashed text-center">
            <LineChartIcon className="h-8 w-8 text-muted-foreground" />
            <p className="mt-3 text-sm font-medium">
              Нет данных для дневного тренда
            </p>
            <p className="mt-1 max-w-md text-xs text-muted-foreground">
              Даже если сводка уже есть, для line graph нужны дневные строки
              mart. После синхронизации график появится автоматически.
            </p>
            <Button asChild size="sm" variant="outline" className="mt-4">
              <Link to={"/operations" as any}>
                Статус синхронизации
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
        )}

        <div className="mt-3 grid gap-2 sm:grid-cols-4">
          <MiniStat
            label={metric.label}
            value={
              <StatWithDelta
                value={currentMetricTotal}
                previousValue={previousMetricTotal}
                inverse={metric.inverse}
              />
            }
            tone={metricComparison.tone}
          />
          <MiniStat
            label="Предыдущий период"
            value={money(previousMetricTotal)}
            tone="neutral"
          />
          <MiniStat
            label="Последний день"
            value={lastPoint ? money(lastPoint[metric.key]) : "—"}
            tone={
              metric.inverse
                ? "warning"
                : (lastPoint?.[metric.key] ?? 0) < 0
                  ? "danger"
                  : "good"
            }
          />
          <MiniStat
            label="Статус расчёта"
            value={summary ? trustLabel(model.trustState) : "—"}
            tone={model.financialFinal ? "good" : "warning"}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function MoneyNowCard({
  loading,
  model,
  previousModel,
  summary,
}: {
  loading: boolean;
  model: ReturnType<typeof buildOwnerModel>;
  previousModel: ReturnType<typeof buildOwnerModel>;
  summary?: MMoneySummary;
}) {
  const [openBreakdown, setOpenBreakdown] =
    useState<ExpenseBreakdownKey | null>(null);
  const [expandedBreakdowns, setExpandedBreakdowns] = useState<
    Record<ExpenseBreakdownKey, boolean>
  >({
    wb: false,
    seller: false,
  });
  const wbBreakdown = useMemo(
    () => buildWbExpenseBreakdown(summary, model),
    [summary, model],
  );
  const sellerBreakdown = useMemo(
    () => buildSellerExpenseBreakdown(summary, model),
    [summary, model],
  );
  const rows: Array<{
    id?: ExpenseBreakdownKey;
    label: string;
    value: number | null;
    previousValue?: number | null;
    tone: "in" | "out" | "bad";
    breakdownTitle?: string;
    breakdown?: ExpenseBreakdownItem[];
    total?: number | null;
  }> = [
    {
      label: "Выручка",
      value: model.revenue,
      previousValue: previousModel.revenue,
      tone: "in",
    },
    {
      id: "wb",
      label: "Расходы WB",
      value: model.expenses == null ? null : -Math.abs(model.expenses),
      previousValue:
        previousModel.expenses == null
          ? null
          : -Math.abs(previousModel.expenses),
      tone: "out",
      breakdownTitle: "Детализация расходов WB",
      breakdown: wbBreakdown,
      total: model.expenses,
    },
    {
      id: "seller",
      label: "Расходы продавца",
      value:
        model.totalSellerCosts == null
          ? null
          : -Math.abs(model.totalSellerCosts),
      previousValue:
        previousModel.totalSellerCosts == null
          ? null
          : -Math.abs(previousModel.totalSellerCosts),
      tone: "out",
      breakdownTitle: "Детализация расходов продавца",
      breakdown: sellerBreakdown,
      total: model.totalSellerCosts,
    },
    {
      label: "Реклама",
      value: model.adSpend == null ? null : -Math.abs(model.adSpend),
      previousValue:
        previousModel.adSpend == null ? null : -Math.abs(previousModel.adSpend),
      tone: "out",
    },
    {
      label: "Чистая прибыль",
      value: model.profit,
      previousValue: previousModel.profit,
      tone: model.profit != null && model.profit < 0 ? "bad" : "in",
    },
  ];
  const maxAbs = Math.max(1, ...rows.map((r) => Math.abs(r.value ?? 0)));

  return (
    <Card className="rounded-lg shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <CircleDollarSign className="h-4 w-4 text-success" />
          Где деньги?
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Итог периода и основные денежные потоки для владельца
        </p>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : (
          <>
            <div className="rounded-lg border bg-muted/30 p-4">
              <div className="text-xs text-muted-foreground">Итог периода</div>
              <div
                className={cn(
                  "mt-1 text-3xl font-semibold tabular-nums",
                  model.profit != null && model.profit < 0
                    ? "text-destructive"
                    : "text-success",
                )}
              >
                {money(model.profit)}
              </div>
              <DeltaBadge
                comparison={compareValue(model.profit, previousModel.profit)}
              />
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>ROI: {formatPercent(model.roi)}</span>
                <span>Маржа: {formatPercent(model.margin)}</span>
                <span>Баланс WB: {money(model.cash)}</span>
              </div>
            </div>

            <div className="space-y-2">
              {rows.map((row) => {
                const isExpandable = Boolean(row.id && row.breakdown?.length);
                const expanded = Boolean(
                  isExpandable && row.id && openBreakdown === row.id,
                );
                return (
                  <div key={row.label} className="space-y-2">
                    <MoneyFlowRow
                      label={row.label}
                      value={row.value}
                      previousValue={row.previousValue}
                      maxAbs={maxAbs}
                      tone={row.tone}
                      expandable={isExpandable}
                      expanded={expanded}
                      onToggle={
                        row.id
                          ? () =>
                              setOpenBreakdown((current) =>
                                current === row.id ? null : row.id!,
                              )
                          : undefined
                      }
                    />
                    {row.id && expanded && row.breakdown?.length ? (
                      <ExpenseBreakdownPanel
                        title={row.breakdownTitle ?? row.label}
                        items={row.breakdown}
                        total={row.total}
                        showAll={expandedBreakdowns[row.id]}
                        onToggleShowAll={() =>
                          setExpandedBreakdowns((current) => ({
                            ...current,
                            [row.id!]: !current[row.id!],
                          }))
                        }
                      />
                    ) : null}
                  </div>
                );
              })}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <MiniStat
                label="Себестоимость"
                value={money(model.cogs)}
                tone="neutral"
              />
              <MiniStat
                label="Прочие расходы"
                value={money(model.sellerOtherExpense)}
                tone="neutral"
              />
            </div>

            {!summary ? (
              <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                Данные `/money/summary` не пришли, поэтому блок денег показан
                ограниченно.
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function TasksCard({
  loading,
  actions,
  model,
}: {
  loading: boolean;
  actions: OwnerItem[];
  model: ReturnType<typeof buildOwnerModel>;
}) {
  const top = actions.slice(0, 6);

  return (
    <Card className="rounded-lg shadow-sm">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <ListChecks className="h-4 w-4 text-primary" />
            Задачи на период
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            Наверху задачи с максимальным влиянием на деньги
          </p>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link to={"/action-center" as any}>
            Все задачи
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="mb-4 grid gap-2 sm:grid-cols-4">
          <MiniStat
            label="Критичные"
            value={model.criticalActions}
            tone={model.criticalActions ? "danger" : "good"}
          />
          <MiniStat
            label="Высокие"
            value={model.highActions}
            tone={model.highActions ? "warning" : "good"}
          />
          <MiniStat
            label="Исправить данные"
            value={model.dataFixActions}
            tone={model.dataFixActions ? "warning" : "good"}
          />
          <MiniStat
            label="Можно действовать"
            value={model.canAct ? "Да" : "Нет"}
            tone={model.canAct ? "good" : "warning"}
          />
        </div>

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : top.length ? (
          <div className="space-y-2">
            {top.map((action, index) => (
              <TaskRow
                key={`${action.id ?? action.action_type ?? "action"}-${index}`}
                action={action}
                index={index}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <CheckCircle2 className="mx-auto h-8 w-8 text-success" />
            <p className="mt-2 text-sm font-medium">Обязательных задач нет</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Если появится новый риск или возможность, они будут здесь.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CardsHealthCard({
  loading,
  cards,
  model,
}: {
  loading: boolean;
  cards: any[];
  model: ReturnType<typeof buildOwnerModel>;
}) {
  const total = cards.length;
  const visible = cards.slice(0, 6);
  const lossCount = model.negativeSku || cardSummaryNum(cards, "loss_count");
  const blocked =
    model.dataBlockedSku || cardSummaryNum(cards, "data_blocked_count");
  const stockRisk =
    model.stockRisk || cardSummaryNum(cards, "stock_risk_count");

  return (
    <Card className="rounded-lg shadow-sm">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <ClipboardCheck className="h-4 w-4 text-info" />
            Состояние карточек и товаров
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            Товарные сигналы, которые влияют на деньги
          </p>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link to={"/products" as any}>
            Товары
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div className="grid grid-cols-3 gap-2">
          <MiniStat
            label="Убыточные"
            value={lossCount}
            tone={lossCount ? "danger" : "good"}
          />
          <MiniStat
            label="Без данных"
            value={blocked}
            tone={blocked ? "warning" : "good"}
          />
          <MiniStat
            label="Риск остатков"
            value={stockRisk}
            tone={stockRisk ? "warning" : "good"}
          />
        </div>

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : visible.length ? (
          <div className="space-y-2">
            {visible.map((card, index) => (
              <CardRiskRow
                key={`${card.sku_id ?? card.nm_id ?? index}`}
                card={card}
                index={index}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <PackageSearch className="mx-auto h-8 w-8 text-muted-foreground" />
            <p className="mt-2 text-sm font-medium">
              Список карточек пока пуст
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              После `/money/articles` или синхронизации товаров здесь появятся
              карточки в риске.
            </p>
          </div>
        )}

        {total > visible.length ? (
          <Button asChild size="sm" variant="ghost" className="w-full">
            <Link to={"/money" as any}>
              Посмотреть ещё {total - visible.length} сигналов
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

function DataTrustPanel({
  loading,
  health,
  blockers,
  model,
}: {
  loading: boolean;
  health?: DashboardDataHealth;
  blockers: any[];
  model: ReturnType<typeof buildOwnerModel>;
}) {
  const sources = buildSourceRows(health, model);
  const trustMessage = buildTrustMessage(model, blockers.length);
  const trustCls = toneClasses(trustMessage.tone);
  const TrustIcon = trustMessage.icon;

  return (
    <Card className="rounded-lg shadow-sm">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <DatabaseZap className="h-4 w-4 text-warning" />
            Доверие к данным
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            Показывает, каким цифрам владелец может доверять
          </p>
        </div>
        <Badge
          variant="outline"
          className={cn(
            "rounded-md",
            model.financialFinal
              ? "border-success/30 text-success"
              : "border-warning/30 text-warning",
          )}
        >
          {model.financialFinal ? "Финально" : "Предварительно"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : (
          <>
            <div className={cn("rounded-lg border p-3", trustCls.soft)}>
              <div className="flex items-start gap-2">
                <TrustIcon className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0">
                  <div className="text-sm font-semibold">
                    {trustMessage.title}
                  </div>
                  <p className="mt-1 text-xs leading-5">
                    {trustMessage.description}
                  </p>
                </div>
              </div>
            </div>

            <div className="grid gap-2 sm:grid-cols-3">
              <MiniStat
                label="Открытые проблемы"
                value={model.openIssues}
                tone={model.openIssues ? "warning" : "good"}
              />
              <MiniStat
                label="Финальные блокеры"
                value={model.finalBlockers}
                tone={model.finalBlockers ? "danger" : "good"}
              />
              <MiniStat
                label="Покрытие себестоимости"
                value={
                  model.costCoverage == null
                    ? "—"
                    : `${model.costCoverage.toFixed(0)}%`
                }
                tone={(model.costCoverage ?? 0) >= 90 ? "good" : "warning"}
              />
            </div>

            {model.costCoverage != null ? (
              <div>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">
                    Покрытие себестоимости
                  </span>
                  <span className="font-medium">
                    {model.costCoverage.toFixed(0)}%
                  </span>
                </div>
                <Progress
                  value={Math.max(0, Math.min(100, model.costCoverage))}
                  className="h-2"
                />
              </div>
            ) : null}

            <div className="divide-y rounded-lg border">
              {sources.map((source) => (
                <div
                  key={source.key}
                  className="flex items-center justify-between gap-3 p-3"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium">{source.label}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {source.affects}
                    </div>
                  </div>
                  <Badge
                    variant="outline"
                    className={cn("shrink-0 rounded-md", source.className)}
                  >
                    {source.status}
                  </Badge>
                </div>
              ))}
            </div>

            {blockers.length ? (
              <div className="rounded-lg border border-warning/30 bg-warning/5 p-3">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <AlertTriangle className="h-4 w-4 text-warning" />
                  Главный блокер данных
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                  {text(
                    blockers[0]?.title,
                    blockers[0]?.simple_reason,
                    blockers[0]?.business_impact,
                  )}
                </p>
                <Button
                  asChild
                  size="sm"
                  variant="outline"
                  className="mt-3 h-7 text-xs"
                >
                  <Link to={"/data-fix" as any}>
                    Исправить данные
                    <ArrowRight className="h-3 w-3" />
                  </Link>
                </Button>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function OwnerNotesPanel({
  owner,
  summary,
  model,
  aiSummary,
  aiLoading,
}: {
  owner?: OwnerDashboard;
  summary?: MMoneySummary;
  model: ReturnType<typeof buildOwnerModel>;
  aiSummary?: OwnerAiSummary;
  aiLoading?: boolean;
}) {
  const localNotes = [
    ...(owner?.notes ?? []),
    summary?.answer?.main_problem,
    summary?.answer?.main_next_step,
  ]
    .filter(Boolean)
    .slice(0, 5) as string[];
  const aiBullets = Array.isArray(aiSummary?.bullets)
    ? aiSummary.bullets.filter(Boolean).slice(0, 4)
    : [];
  const notes = aiBullets.length ? aiBullets : localNotes;
  const summaryMode =
    aiSummary?.mode === "ai"
      ? "ИИ"
      : aiSummary?.configured === false
        ? "Локальная"
        : "Сводка";
  const StatusIcon = model.status.icon;
  const statusCls = toneClasses(model.status.tone);
  const headline = text(aiSummary?.title, model.ownerTitle, model.status.title);
  const description = text(
    model.ownerReason,
    notes[0],
    model.status.description,
  );
  const decisionSteps = buildBriefingSteps(notes, model);
  const generatedAt = aiSummary?.generated_at ?? model.updatedAt;
  const sourceText = aiLoading
    ? "Сводка обновляется"
    : aiSummary?.mode === "ai"
      ? "ИИ по данным панели владельца"
      : "Локальная сводка";

  const insightCards = [
    {
      label: "Деньги",
      value: money(model.profit),
      hint: [
        model.revenue != null
          ? `Выручка ${formatMoneyCompact(model.revenue)}`
          : "",
        model.margin != null ? `Маржа ${model.margin.toFixed(1)}%` : "",
      ]
        .filter(Boolean)
        .join(" · "),
      tone: model.profitTone,
      icon: CircleDollarSign,
    },
    {
      label: "Риск",
      value: model.riskMoney
        ? formatMoneyCompact(model.riskMoney)
        : `${formatNumber(model.totalRiskSku)} SKU`,
      hint: [
        model.overstock ? `Остатки ${formatMoneyCompact(model.overstock)}` : "",
        model.negativeSku ? `Убыточные ${formatNumber(model.negativeSku)}` : "",
      ]
        .filter(Boolean)
        .join(" · "),
      tone:
        model.criticalActions || model.negativeSku
          ? "danger"
          : model.totalRiskSku
            ? "warning"
            : "good",
      icon: ShieldAlert,
    },
    {
      label: "Фокус",
      value: model.urgentActions ? `${model.urgentActions} задач` : "Спокойно",
      hint: clipText(
        model.todayFocus ||
          (model.financialFinal
            ? "Можно смотреть рост и товары"
            : "Сначала проверьте данные"),
        68,
      ),
      tone: model.urgentActions ? "warning" : "good",
      icon: ListChecks,
    },
  ];

  return (
    <Card className="rounded-lg shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4 text-success" />
              Краткая сводка
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              Короткий управленческий вывод по деньгам, рискам и действиям
            </p>
          </div>
          <Badge variant="outline" className="shrink-0 rounded-md">
            {aiLoading ? "Готовится" : summaryMode}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div className={cn("rounded-lg border p-4", statusCls.soft)}>
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border bg-background/70">
              {StatusIcon ? (
                <StatusIcon className="h-4 w-4" />
              ) : (
                <BadgeCheck className="h-4 w-4" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant="outline"
                  className="rounded-md bg-background/70"
                >
                  {model.status.label}
                </Badge>
                {generatedAt ? (
                  <span className="text-xs text-muted-foreground">
                    {sourceText} · {formatDateTime(generatedAt)}
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground">
                    {sourceText}
                  </span>
                )}
              </div>
              <div className="mt-2 text-base font-semibold leading-6">
                {clipText(headline, 120)}
              </div>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                {clipText(description, 190)}
              </p>
            </div>
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-3">
          {insightCards.map((item) => {
            const Icon = item.icon;
            const cls = toneClasses(item.tone as MetricTone);
            return (
              <div key={item.label} className="rounded-lg border p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground">
                    {item.label}
                  </span>
                  <span
                    className={cn(
                      "flex h-7 w-7 items-center justify-center rounded-md border",
                      cls.soft,
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </span>
                </div>
                <div className="mt-2 text-sm font-semibold">{item.value}</div>
                <div className="mt-1 min-h-4 truncate text-xs text-muted-foreground">
                  {item.hint || "—"}
                </div>
              </div>
            );
          })}
        </div>

        {aiLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 2 }).map((_, index) => (
              <Skeleton key={index} className="h-14 w-full" />
            ))}
          </div>
        ) : decisionSteps.length ? (
          <div className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Решения на сегодня
            </div>
            {decisionSteps.map((note, index) => (
              <div
                key={`${note}-${index}`}
                className="flex gap-3 rounded-lg border p-3 text-sm transition hover:bg-muted/25"
              >
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border bg-primary/10 text-[11px] font-semibold text-primary">
                  {index + 1}
                </span>
                <span className="leading-6 text-muted-foreground">
                  {clipText(note, 180)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <CalendarDays className="mx-auto h-8 w-8 text-muted-foreground" />
            <p className="mt-2 text-sm font-medium">
              Сводка ещё не сформирована
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              После первой полной синхронизации и аудита бизнес-вывод появится
              здесь.
            </p>
          </div>
        )}
        {aiSummary?.warnings?.length ? (
          <div className="rounded-md border border-warning/30 bg-warning/5 p-2 text-xs text-muted-foreground">
            ИИ-сводка сейчас недоступна, показана локальная сводка по данным
            панели владельца.
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function buildBriefingSteps(
  notes: string[],
  model: ReturnType<typeof buildOwnerModel>,
): string[] {
  const fallback = [
    model.todayFocus ? `Сначала: ${model.todayFocus}` : "",
    model.finalBlockers || model.blockerCount
      ? "Закройте блокеры данных, чтобы прибыль стала финальной и пригодной для управленческих решений."
      : "",
    model.overstock
      ? `Проверьте замороженный остаток: в товаре около ${formatMoneyCompact(model.overstock)}.`
      : "",
    model.negativeSku
      ? `Разберите убыточные карточки: сейчас в минусе ${formatNumber(model.negativeSku)} SKU.`
      : "",
    model.adSpend && model.revenue
      ? `Проверьте рекламу: расход ${formatMoneyCompact(model.adSpend)} при выручке ${formatMoneyCompact(model.revenue)}.`
      : "",
  ];
  const unique = new Set<string>();
  return [...notes, ...fallback]
    .map((value) => value.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .filter((value) => {
      const key = value.toLowerCase();
      if (unique.has(key)) return false;
      unique.add(key);
      return true;
    })
    .slice(0, 3);
}

function clipText(value: string, max: number): string {
  if (!value || value.length <= max) return value;
  return `${value.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

function TaskRow({ action, index }: { action: OwnerItem; index: number }) {
  const priority = String(action.priority ?? "medium").toLowerCase();
  const amount = num(action.expected_effect_amount);
  const title = text(
    action.title,
    action.what_to_do,
    action.action_type,
    "Задача",
  );
  const reason = text(
    action.reason,
    action.why,
    action.what_to_do,
    "Сигнал, который влияет на бизнес",
  );
  const id = action.id;

  return (
    <Link
      to={"/action-center" as any}
      search={(id ? { id } : undefined) as any}
      className="grid gap-3 rounded-lg border bg-card p-3 transition hover:border-primary/40 hover:bg-muted/30 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:grid-cols-[36px_minmax(0,1fr)_auto] sm:items-center"
    >
      <div
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-md border text-xs font-semibold",
          priorityClass(priority),
        )}
      >
        {index + 1}
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            variant="outline"
            className={cn("rounded-md text-[10px]", priorityClass(priority))}
          >
            {priorityLabel(priority)}
          </Badge>
          {action.category ? (
            <Badge variant="outline" className="rounded-md text-[10px]">
              {actionCategoryLabel(action.category)}
            </Badge>
          ) : null}
          {amount != null ? (
            <span className="text-xs font-medium text-success">
              {formatMoneyCompact(amount)}
            </span>
          ) : null}
        </div>
        <div className="mt-1 line-clamp-2 text-sm font-medium">{title}</div>
        <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
          {reason}
        </div>
      </div>
      <span className="flex h-8 w-8 items-center justify-center rounded-md border bg-background text-muted-foreground">
        <ArrowRight className="h-3.5 w-3.5" />
      </span>
    </Link>
  );
}

function CardRiskRow({ card, index }: { card: any; index: number }) {
  const moneyBlock = card.money ?? {};
  const profit = num(
    moneyBlock?.profit?.after_source_ads,
    moneyBlock?.profit?.after_ads,
    moneyBlock?.profit?.after_allocated_ads,
    card.net_profit,
  );
  const revenue = num(moneyBlock?.revenue, card.revenue);
  const title = text(
    card.title,
    card.vendor_code,
    card.nm_id ? `NM ${card.nm_id}` : null,
    "Карточка",
  );
  const verdict = text(
    card.business_verdict?.label,
    card.business_verdict?.status,
    card.status,
    "Сигнал",
  );
  const riskTone: MetricTone =
    profit == null ? "neutral" : profit < 0 ? "danger" : "good";
  const imageCandidates = cardImageCandidates(card);
  const [imageIndex, setImageIndex] = useState(0);
  const imageSrc =
    imageIndex < imageCandidates.length ? imageCandidates[imageIndex] : null;
  const linkProps = card.nm_id
    ? { to: "/products/$nmId" as const, params: { nmId: String(card.nm_id) } }
    : { to: "/products" as const };

  return (
    <Link
      {...(linkProps as any)}
      aria-label={`Открыть карточку: ${title}`}
      className={cn(
        "grid grid-cols-[52px_minmax(0,1fr)_auto_24px] items-center gap-3 rounded-lg border p-2.5 transition hover:bg-muted/25 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        riskTone === "danger"
          ? "border-destructive/30 hover:border-destructive/50"
          : riskTone === "good"
            ? "border-success/30 hover:border-success/50"
            : "border-info/30 hover:border-info/50",
      )}
    >
      <div
        className={cn(
          "relative flex h-14 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted",
          riskTone === "danger"
            ? "border-destructive/35 bg-destructive/5"
            : riskTone === "good"
              ? "border-success/35 bg-success/5"
              : "border-info/35 bg-info/5",
        )}
      >
        {imageSrc ? (
          <img
            src={imageSrc}
            alt={title}
            loading="lazy"
            className="h-full w-full object-cover"
            onError={() => setImageIndex((current) => current + 1)}
          />
        ) : (
          <PackageSearch className="h-5 w-5 text-muted-foreground" />
        )}
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{title}</div>
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
          <span>{verdict}</span>
          {card.nm_id ? <span>NM {card.nm_id}</span> : null}
          {card.vendor_code ? <span>{card.vendor_code}</span> : null}
        </div>
      </div>
      <div className="text-right">
        <div
          className={cn(
            "text-sm font-semibold tabular-nums",
            profit != null && profit < 0 ? "text-destructive" : "",
          )}
        >
          {money(profit)}
        </div>
        <div className="text-xs text-muted-foreground">
          {revenue != null ? formatMoneyCompact(revenue) : "—"} выручка
        </div>
      </div>
      <div className="flex h-7 w-7 items-center justify-center rounded-md border bg-background text-muted-foreground">
        <ArrowRight className="h-3.5 w-3.5" />
      </div>
    </Link>
  );
}

function cardImageCandidates(card: Record<string, any>): string[] {
  const direct = [
    card.thumbnail,
    card.thumbnail_url,
    card.display_photo_url,
    card.proxy_photo_url,
    card.main_photo_url,
    card.image_url,
    card.photo_url,
    card.photo,
    firstArrayImage(card.photos),
    firstArrayImage(card.images),
    firstArrayImage(card.raw?.photos),
    firstArrayImage(card.raw?.identity?.photos),
  ].filter((value): value is string => typeof value === "string" && !!value);
  const generated = wbImageCandidates(card.nm_id);
  const primary = direct[0] ?? generated[0];
  return primary ? [proxyWbImageUrl(primary)] : [];
}

function firstArrayImage(value: unknown): string | null {
  if (!Array.isArray(value)) return null;
  for (const item of value) {
    if (typeof item === "string" && item.trim()) return item.trim();
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    for (const key of [
      "big",
      "canonical_url",
      "url",
      "full",
      "photo",
      "src",
      "c516x688",
      "square",
      "c246x328",
      "tm",
      "thumbnail",
      "preview",
    ]) {
      const raw = record[key];
      if (typeof raw === "string" && raw.trim()) return raw.trim();
    }
  }
  return null;
}

function wbImageCandidates(nmId: unknown): string[] {
  const n = Number(nmId);
  if (!Number.isFinite(n) || n <= 0) return [];
  const vol = Math.floor(n / 100000);
  const part = Math.floor(n / 1000);
  const host = wbBasketHost(vol);
  return [
    `https://${host}/vol${vol}/part${part}/${n}/images/c246x328/1.webp`,
  ];
}

function wbBasketHost(vol: number): string {
  const ranges: [number, number][] = [
    [143, 1],
    [287, 2],
    [431, 3],
    [719, 4],
    [1007, 5],
    [1061, 6],
    [1115, 7],
    [1169, 8],
    [1313, 9],
    [1601, 10],
    [1655, 11],
    [1919, 12],
    [2045, 13],
    [2189, 14],
    [2405, 15],
    [2621, 16],
    [2837, 17],
    [3053, 18],
    [3269, 19],
    [3485, 20],
    [3701, 21],
    [3917, 22],
    [4133, 23],
    [4349, 24],
    [4565, 25],
    [4877, 26],
    [5189, 27],
    [5509, 28],
    [5825, 29],
    [6141, 30],
  ];
  const basket = ranges.find(([maxVol]) => vol <= maxVol)?.[1] ?? 30;
  return `basket-${String(basket).padStart(2, "0")}.wbbasket.ru`;
}

function proxyWbImageUrl(src: string): string {
  return src;
}

function MiniStat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  tone?: MetricTone;
}) {
  const cls = toneClasses(tone);
  return (
    <div className={cn("rounded-md border p-2", cls.soft)}>
      <div className="truncate text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 truncate text-sm font-semibold tabular-nums">
        {value}
      </div>
    </div>
  );
}

function DeltaBadge({ comparison }: { comparison: ComparisonValue }) {
  const DiffIcon =
    comparison.diff == null
      ? BadgeCheck
      : comparison.diff >= 0
        ? TrendingUp
        : TrendingDown;
  return (
    <div
      className={cn(
        "mt-1 inline-flex max-w-full items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium",
        toneClasses(comparison.tone).soft,
      )}
    >
      <DiffIcon className="h-3 w-3 shrink-0" />
      <span className="truncate">{comparison.label}</span>
    </div>
  );
}

function MetricComparisonBlock({
  comparison,
  previousValue,
}: {
  comparison: ComparisonValue;
  previousValue?: number | null;
}) {
  return (
    <div className="mt-2 space-y-1">
      <div
        className="text-[11px] text-muted-foreground"
        title={`Предыдущий период: ${money(previousValue)}`}
      >
        Было:{" "}
        <span className="font-medium tabular-nums text-foreground">
          {previousValue == null ? "—" : formatMoneyCompact(previousValue)}
        </span>
      </div>
      <DeltaBadge comparison={comparison} />
    </div>
  );
}

function StatWithDelta({
  value,
  previousValue,
  inverse = false,
}: {
  value: number | null;
  previousValue: number | null;
  inverse?: boolean;
}) {
  const comparison = compareValue(value, previousValue, inverse);
  return (
    <span className="inline-flex min-w-0 flex-col">
      <span>{money(value)}</span>
      <span className="truncate text-[11px] font-medium text-muted-foreground">
        {comparison.label}
      </span>
    </span>
  );
}

function MoneyFlowRow({
  label,
  value,
  previousValue,
  maxAbs,
  tone,
  expandable = false,
  expanded = false,
  onToggle,
}: {
  label: string;
  value: number | null;
  previousValue?: number | null;
  maxAbs: number;
  tone: "in" | "out" | "bad";
  expandable?: boolean;
  expanded?: boolean;
  onToggle?: () => void;
}) {
  const width =
    value == null
      ? 0
      : Math.max(6, Math.min(100, (Math.abs(value) / maxAbs) * 100));
  const color =
    tone === "out"
      ? "bg-destructive"
      : tone === "bad"
        ? "bg-destructive"
        : "bg-success";
  const content = (
    <>
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="flex min-w-0 items-center gap-1.5 text-muted-foreground">
          {expandable ? (
            expanded ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            )
          ) : null}
          <span className="truncate">{label}</span>
        </span>
        <span className="text-right">
          <span
            className={cn(
              "block font-medium tabular-nums",
              value != null && value < 0 ? "text-destructive" : "",
            )}
          >
            {money(value)}
          </span>
          <span className="block text-[11px] text-muted-foreground">
            {
              compareValue(
                value == null ? null : Math.abs(value),
                previousValue == null ? null : Math.abs(previousValue),
                tone === "out",
              ).label
            }
          </span>
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full", color)}
          style={{ width: `${width}%` }}
        />
      </div>
    </>
  );

  if (expandable) {
    return (
      <button
        type="button"
        className="w-full space-y-1.5 rounded-md px-2 py-2 text-left transition hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-expanded={expanded}
        onClick={onToggle}
      >
        {content}
      </button>
    );
  }

  return <div className="space-y-1.5 px-2 py-1">{content}</div>;
}

function ExpenseBreakdownPanel({
  title,
  items,
  total,
  showAll,
  onToggleShowAll,
}: {
  title: string;
  items: ExpenseBreakdownItem[];
  total?: number | null;
  showAll: boolean;
  onToggleShowAll: () => void;
}) {
  const sorted = [...items]
    .filter((item) => Number.isFinite(item.value) && Math.abs(item.value) > 0)
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  const visible = showAll ? sorted : sorted.slice(0, 4);
  const hiddenCount = Math.max(0, sorted.length - visible.length);
  const max = Math.max(1, ...sorted.map((item) => Math.abs(item.value)));
  const totalAmount =
    total == null || !Number.isFinite(total)
      ? sum(sorted.map((item) => item.value))
      : total;

  return (
    <div className="rounded-md border bg-muted/20 px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold text-foreground">
            {title}
          </div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            Итого по статье:{" "}
            <span className="font-medium tabular-nums text-destructive">
              {money(-Math.abs(totalAmount))}
            </span>
          </div>
        </div>
        <Badge variant="outline" className="shrink-0 rounded-md">
          {sorted.length} статей
        </Badge>
      </div>

      <div className="mt-3 space-y-2.5">
        {visible.map((item) => {
          const width = Math.max(7, (Math.abs(item.value) / max) * 100);
          const isOffset = item.value < 0;
          return (
            <div key={`${item.key}-${item.label}`} className="space-y-1">
              <div className="flex items-start justify-between gap-3 text-xs">
                <span className="min-w-0">
                  <span className="block truncate font-medium">
                    {item.label}
                  </span>
                  {item.description ? (
                    <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                      {item.description}
                      {isOffset ? " Уменьшает общий расход." : ""}
                    </span>
                  ) : null}
                </span>
                <span
                  className={cn(
                    "shrink-0 font-semibold tabular-nums",
                    isOffset ? "text-success" : "text-destructive",
                  )}
                >
                  {expenseSignedMoney(item.value)}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-background">
                <div
                  className={cn(
                    "h-full rounded-full",
                    isOffset ? "bg-success/75" : "bg-destructive/75",
                  )}
                  style={{ width: `${Math.min(100, width)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {sorted.length > 4 ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="mt-2 h-7 px-2 text-xs"
          onClick={onToggleShowAll}
        >
          {showAll ? "Свернуть" : `Показать ещё ${hiddenCount}`}
        </Button>
      ) : null}
    </div>
  );
}

const SELLER_EXPENSE_KEYS = new Set(["seller_cogs", "seller_other_expense"]);
const AD_ONLY_EXPENSE_KEYS = new Set([
  "ads_operational",
  "marketing_deduction",
  "ad_spend",
  "ad_spend_final",
]);

function buildWbExpenseBreakdown(
  summary: MMoneySummary | undefined,
  model: ReturnType<typeof buildOwnerModel>,
): ExpenseBreakdownItem[] {
  const k = summary?.kpis as any;
  const breakdown = summary?.expense_breakdown as any;
  const total = num(
    model.expenses,
    breakdown?.total_wb_expenses,
    k?.wb_expenses_total,
    k?.direct_wb_expenses,
  );
  const fromSummary = summaryExpenseItems(summary).filter((item) =>
    isWbExpenseKey(item.key),
  );
  const items = fromSummary.length
    ? fromSummary
    : [
        expenseItem(
          "wb_commission",
          "Комиссия WB",
          num(k?.wb_commission, k?.commission),
        ),
        expenseItem(
          "payment_processing",
          "Эквайринг",
          num(k?.payment_processing, k?.acquiring_fee),
        ),
        expenseItem("pvz_reward", "Вознаграждение ПВЗ", num(k?.pvz_reward)),
        expenseItem(
          "wb_logistics",
          "Логистика WB",
          num(k?.wb_logistics, k?.logistics),
        ),
        expenseItem(
          "wb_logistics_rebill",
          "Перерасчёт логистики",
          num(k?.wb_logistics_rebill),
        ),
        expenseItem(
          "acceptance",
          "Платная приёмка",
          num(k?.acceptance, k?.paid_acceptance),
        ),
        expenseItem("storage", "Хранение", num(k?.storage)),
        expenseItem("penalty", "Штрафы", num(k?.penalty, k?.penalties)),
        expenseItem("deduction", "Удержания", num(k?.deduction, k?.deductions)),
        expenseItem("loyalty", "Лояльность и кешбэк", num(k?.loyalty)),
        expenseItem(
          "other_wb_expenses",
          "Прочие WB расходы",
          num(k?.other_wb_expenses, k?.unclassified_wb_expenses, k?.wb_other),
        ),
      ];

  return completeExpenseBreakdown(items, total, "Не распределено в деталях");
}

function buildSellerExpenseBreakdown(
  summary: MMoneySummary | undefined,
  model: ReturnType<typeof buildOwnerModel>,
): ExpenseBreakdownItem[] {
  const k = summary?.kpis as any;
  const breakdown = summary?.expense_breakdown as any;
  const total = num(
    model.totalSellerCosts,
    breakdown?.total_seller_expenses,
    k?.total_seller_costs,
    k?.total_seller_expenses,
  );
  const fromSummary = summaryExpenseItems(summary).filter((item) =>
    SELLER_EXPENSE_KEYS.has(item.key),
  );
  const items = fromSummary.length
    ? fromSummary
    : [
        expenseItem(
          "seller_cogs",
          "Себестоимость товара",
          num(k?.seller_cogs, model.cogs),
        ),
        expenseItem(
          "seller_other_expense",
          "Прочие расходы продавца",
          num(k?.seller_other_expense, model.sellerOtherExpense),
        ),
      ];

  return completeExpenseBreakdown(items, total, "Продавец: не распределено");
}

function summaryExpenseItems(
  summary: MMoneySummary | undefined,
): ExpenseBreakdownItem[] {
  const items = ((summary?.expense_breakdown as any)?.items ?? []) as any[];
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      const key = String(
        item?.category ?? item?.group_key ?? item?.key ?? "",
      ).trim();
      const value = num(item?.amount);
      if (!key || value == null || value === 0) return null;
      return {
        key,
        label: text(item?.label, item?.category_label, expenseLabel(key)),
        value,
        description: expenseDescription(key, item?.source),
        final: typeof item?.is_final === "boolean" ? item.is_final : null,
      } satisfies ExpenseBreakdownItem;
    })
    .filter(Boolean) as ExpenseBreakdownItem[];
}

function isWbExpenseKey(key: string) {
  return (
    Boolean(key) &&
    !SELLER_EXPENSE_KEYS.has(key) &&
    !AD_ONLY_EXPENSE_KEYS.has(key)
  );
}

function expenseItem(
  key: string,
  label: string,
  value: number | null,
): ExpenseBreakdownItem {
  return {
    key,
    label,
    value: value ?? 0,
    description: expenseDescription(key),
  };
}

function completeExpenseBreakdown(
  items: ExpenseBreakdownItem[],
  total: number | null,
  remainderLabel: string,
): ExpenseBreakdownItem[] {
  const merged = new Map<string, ExpenseBreakdownItem>();
  for (const item of items) {
    const value = item.value;
    if (!Number.isFinite(value) || value === 0) continue;
    const key = item.key || item.label;
    const current = merged.get(key);
    if (current) {
      current.value += value;
    } else {
      merged.set(key, { ...item, value });
    }
  }
  const clean = [...merged.values()];
  const listed = sum(clean.map((item) => item.value));
  const totalValue = total ?? listed;
  const gap = totalValue - listed;
  const minGap = Math.max(1, Math.abs(totalValue) * 0.005);
  if (Math.abs(gap) > minGap) {
    clean.push({
      key: `${remainderLabel}-remainder`,
      label: remainderLabel,
      value: gap,
      description:
        gap >= 0
          ? "Сумма есть в общем итоге, но без отдельной статьи."
          : "Корректировка уменьшает общий расход.",
    });
  }
  return clean.sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
}

function expenseLabel(key: string) {
  const labels: Record<string, string> = {
    wb_logistics: "Логистика WB",
    wb_logistics_rebill: "Перерасчёт логистики",
    storage: "Хранение",
    acceptance: "Платная приёмка",
    wb_commission: "Комиссия WB",
    payment_processing: "Эквайринг",
    pvz_reward: "Вознаграждение ПВЗ",
    penalty: "Штрафы",
    deduction: "Удержания",
    marketing_deduction: "Продвижение WB",
    loyalty: "Лояльность и кешбэк",
    other_wb_expenses: "Прочие WB расходы",
    wb_other: "Прочие WB расходы",
    unclassified_wb_expenses: "Неразобранные WB расходы",
    seller_cogs: "Себестоимость товара",
    seller_other_expense: "Прочие расходы продавца",
  };
  return labels[key] ?? key;
}

function expenseDescription(key: string, source?: unknown) {
  const descriptions: Record<string, string> = {
    wb_logistics: "Доставка, возвраты и логистика marketplace.",
    wb_logistics_rebill: "Перевыставленная логистика и корректировки.",
    storage: "Плата за хранение на складах WB.",
    acceptance: "Платная приёмка поставок.",
    wb_commission: "Комиссия marketplace с продаж.",
    payment_processing: "Эквайринг и обработка платежей.",
    pvz_reward: "Вознаграждение пунктов выдачи заказов.",
    penalty: "Штрафы и санкции WB.",
    deduction: "Удержания и корректировки отчёта.",
    marketing_deduction: "Продвижение, удержанное в финансовом отчёте WB.",
    loyalty: "Лояльность, кешбэк и скидочные механики.",
    other_wb_expenses: "Прочие расходы WB за выбранный период.",
    unclassified_wb_expenses:
      "Расходы, которые backend не смог разложить точнее.",
    seller_cogs: "Закупочная себестоимость проданных товаров.",
    seller_other_expense: "Упаковка, фулфилмент и ручные расходы продавца.",
  };
  const description = descriptions[key];
  if (description) return description;
  return typeof source === "string" && source ? `Источник: ${source}` : "";
}

function TrendTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload as ComparisonTrendPoint | undefined;
  return (
    <div className="rounded-lg border bg-card p-3 text-xs shadow-lg">
      <div className="mb-2 space-y-0.5 font-medium">
        <div>{label}</div>
        {point?.previousLabel ? (
          <div className="text-[11px] font-normal text-muted-foreground">
            Предыдущий период: {point.previousLabel}
          </div>
        ) : null}
      </div>
      <div className="space-y-1.5">
        {payload.map((item: any) => (
          <div
            key={item.dataKey}
            className="flex items-center justify-between gap-6"
          >
            <span className="flex items-center gap-2 text-muted-foreground">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: item.stroke }}
              />
              {item.name}
            </span>
            <span className="font-medium tabular-nums">
              {formatMoney(item.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function buildComparisonTrend(
  current: TrendPoint[],
  previous: TrendPoint[],
): ComparisonTrendPoint[] {
  const max = Math.max(current.length, previous.length);
  const result: ComparisonTrendPoint[] = [];
  for (let index = 0; index < max; index += 1) {
    const currentPoint = current[index];
    const previousPoint = previous[index];
    const date =
      currentPoint?.date ??
      (previousPoint ? addDaysIso(previousPoint.date, current.length) : "");
    if (!date) continue;
    result.push({
      date,
      label: currentPoint?.label ?? `${index + 1}`,
      revenue: currentPoint?.revenue ?? 0,
      payout: currentPoint?.payout ?? 0,
      expenses: currentPoint?.expenses ?? 0,
      ads: currentPoint?.ads ?? 0,
      profit: currentPoint?.profit ?? 0,
      previousDate: previousPoint?.date,
      previousLabel: previousPoint?.label,
      previousRevenue: previousPoint?.revenue,
      previousPayout: previousPoint?.payout,
      previousProfit: previousPoint?.profit,
      previousExpenses: previousPoint?.expenses,
      previousAds: previousPoint?.ads,
    });
  }
  return result;
}

function previousTrendDataKey(key: TrendMetricKey) {
  const map: Record<TrendMetricKey, keyof ComparisonTrendPoint> = {
    revenue: "previousRevenue",
    payout: "previousPayout",
    profit: "previousProfit",
    expenses: "previousExpenses",
    ads: "previousAds",
  };
  return map[key];
}

function sumTrendMetric(points: TrendPoint[], key: TrendMetricKey) {
  return sum(points.map((point) => point[key]));
}

function buildTrendPoints(dailyData: any): TrendPoint[] {
  const map = new Map<string, TrendPoint>();
  const ensure = (date: string) => {
    const key = date.slice(0, 10);
    if (!map.has(key)) {
      map.set(key, {
        date: key,
        label: formatShortDate(key),
        revenue: 0,
        payout: 0,
        expenses: 0,
        ads: 0,
        profit: 0,
      });
    }
    return map.get(key)!;
  };

  for (const row of getItems(dailyData)) {
    const date = String(row?.stat_date ?? row?.date ?? "");
    if (!date) continue;
    const point = ensure(date);
    point.revenue +=
      num(row?.revenue, row?.final_revenue, row?.revenue_final) ?? 0;
    point.payout +=
      num(row?.payout, row?.final_for_pay, row?.finance_for_pay) ?? 0;
    point.ads +=
      num(
        row?.ad_spend_operational,
        row?.source_ad_spend,
        row?.ads_source_spend,
        row?.ad_spend,
        row?.ad_spend_final,
      ) ?? 0;
    const dailyExpenses =
      num(row?.expenses) ??
      sum([
        num(row?.total_wb_expenses, row?.total_expense),
        num(row?.total_seller_costs, row?.total_seller_expenses),
        num(
          row?.ad_spend_operational,
          row?.source_ad_spend,
          row?.ads_source_spend,
          row?.ad_spend,
          row?.ad_spend_final,
          row?.marketing_deduction,
        ),
      ]);
    point.expenses += dailyExpenses;
    const explicitProfit = num(row?.profit, row?.net_profit_after_all_expenses);
    if (explicitProfit != null) {
      point.profit += explicitProfit;
    } else {
      point.profit +=
        (point.payout || point.revenue) -
        dailyExpenses +
        (num(row?.additional_income) ?? 0);
    }
  }

  return [...map.values()].sort((a, b) => a.date.localeCompare(b.date));
}

function extractActions(
  data: any,
  owner?: OwnerDashboard,
  summary?: MMoneySummary,
): OwnerItem[] {
  const fromEndpoint = Array.isArray(data?.owner_focus_actions)
    ? data.owner_focus_actions
    : Array.isArray(data?.items)
      ? data.items
      : Array.isArray(data)
        ? data
        : [];
  const ownerPreview = [
    ...(owner?.next_actions_preview ?? []),
    ...(owner?.top_risks ?? []),
    ...(owner?.top_opportunities ?? []),
  ];
  const summaryActions = Array.isArray(summary?.next_actions)
    ? summary.next_actions
    : [];
  const combined = [
    ...fromEndpoint,
    ...ownerPreview,
    ...summaryActions,
  ] as OwnerItem[];
  const seen = new Set<string>();
  return combined
    .filter(Boolean)
    .filter((action) => {
      const key = String(
        action.id ??
          `${action.action_type ?? ""}-${action.sku_id ?? ""}-${action.nm_id ?? ""}-${action.title ?? ""}`,
      );
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => actionRank(b) - actionRank(a));
}

function extractBlockers(
  data: MDataBlockersResponse | null | undefined,
): any[] {
  if (!data) return [];
  if (Array.isArray(data.blockers)) return data.blockers;
  return [];
}

function extractCards(
  data: Paginated<MCardItem> | MCardItem[] | null | undefined,
  summary?: MMoneySummary,
): any[] {
  const endpointCards = getItems(data);
  if (endpointCards.length) {
    (endpointCards as any).__summary = (data as any)?.summary;
    return endpointCards;
  }
  const top = summary?.top_cards;
  if (!top) return [];
  return [
    ...(top.loss_making ?? []),
    ...(top.data_blocked ?? []),
    ...(top.stock_risk ?? []),
    ...(top.profitable ?? []),
  ].slice(0, 8);
}

function buildSourceRows(
  health: DashboardDataHealth | undefined,
  model: ReturnType<typeof buildOwnerModel>,
) {
  const failed = new Set(
    (health?.failed_domains ?? []).map((x) => String(x).toLowerCase()),
  );
  const skipped = new Set(
    (health?.skipped_domains ?? []).map((x) => String(x).toLowerCase()),
  );
  const domains = (health?.domains ?? []).map((d: any) =>
    String(d.domain ?? d.name ?? "").toLowerCase(),
  );
  const status = (patterns: string[]) => {
    if (!health)
      return {
        status: "Нет данных",
        className: "border-muted text-muted-foreground",
      };
    if (patterns.some((p) => [...failed].some((x) => x.includes(p))))
      return {
        status: "Нужна синхронизация",
        className: "border-destructive/30 text-destructive",
      };
    if (patterns.some((p) => [...skipped].some((x) => x.includes(p))))
      return {
        status: "Нет источника",
        className: "border-warning/30 text-warning",
      };
    if (patterns.some((p) => domains.some((x) => x.includes(p))))
      return { status: "OK", className: "border-success/30 text-success" };
    return {
      status: "Неизвестно",
      className: "border-muted text-muted-foreground",
    };
  };

  const cost =
    model.costCoverage == null
      ? {
          status: "Нет данных",
          className: "border-warning/30 text-warning",
        }
      : model.costCoverage >= 90
        ? {
            status: `${model.costCoverage.toFixed(0)}%`,
            className: "border-success/30 text-success",
          }
        : {
            status: `${model.costCoverage.toFixed(0)}%`,
            className: "border-warning/30 text-warning",
          };

  return [
    {
      key: "finance",
      label: "Финансы WB",
      affects: "Выручка, выплаты, чистая прибыль",
      ...status(["finance", "reconcil", "report"]),
    },
    {
      key: "sales",
      label: "Продажи и заказы",
      affects: "Заказы, продажи, возвраты",
      ...status(["sale", "order", "realiz"]),
    },
    {
      key: "cards",
      label: "Карточки и товары",
      affects: "Название, артикул, связка SKU",
      ...status(["card", "product", "nomen"]),
    },
    {
      key: "stock",
      label: "Остатки",
      affects: "Стоимость склада, риск дефицита",
      ...status(["stock", "warehouse", "invent"]),
    },
    {
      key: "cost",
      label: "Себестоимость",
      affects: "Прибыль, маржа, ROI",
      ...cost,
    },
    {
      key: "ads",
      label: "Реклама",
      affects: "DRR, распределение рекламы, прибыль",
      ...status(["ads", "advert", "campaign"]),
    },
  ];
}

function buildTrustMessage(
  model: ReturnType<typeof buildOwnerModel>,
  blockersCount: number,
) {
  if (model.financialFinal) {
    return {
      tone: "good" as MetricTone,
      icon: CheckCircle2,
      title: "Финальные цифры готовы для решений",
      description:
        "Выручка, расходы и прибыль прошли финальную сверку. Можно использовать эти суммы для управленческих решений.",
    };
  }
  if (model.finalBlockers > 0 || blockersCount > 0) {
    return {
      tone: "warning" as MetricTone,
      icon: AlertTriangle,
      title: "Прибыль пока предварительная",
      description:
        "Операционные решения принимать можно, но финальную прибыль лучше не фиксировать: есть блокеры данных или сверки.",
    };
  }
  if ((model.costCoverage ?? 0) < 90) {
    return {
      tone: "warning" as MetricTone,
      icon: DatabaseZap,
      title: "Не хватает себестоимости",
      description:
        "Часть товаров не имеет подтверждённой себестоимости. Маржа, ROI и прибыль могут измениться после заполнения данных.",
    };
  }
  return {
    tone: "info" as MetricTone,
    icon: Gauge,
    title: "Данные операционные",
    description:
      "Система уже показывает направление бизнеса, но часть источников ещё может обновиться после синхронизации.",
  };
}

function actionRank(action: OwnerItem) {
  const priority = String(action.priority ?? "").toLowerCase();
  const p =
    priority === "critical"
      ? 400
      : priority === "high"
        ? 300
        : priority === "medium"
          ? 200
          : priority === "low"
            ? 100
            : 0;
  return (
    p + Math.min(99, Math.abs(num(action.expected_effect_amount) ?? 0) / 1000)
  );
}

function countByPriority(actions: OwnerItem[], priority: string) {
  return actions.filter(
    (a) => String(a.priority ?? "").toLowerCase() === priority,
  ).length;
}

function sumRiskAmount(summary?: MMoneySummary) {
  const risks = (summary?.risk_summary?.risks ?? []) as any[];
  return sum(
    risks.map((r) => num(r?.affected_amount, r?.amount_at_risk, r?.amount)),
  );
}

function getItems(data: any): any[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  if (Array.isArray(data.items)) return data.items;
  return [];
}

function cardSummaryNum(cards: any[], key: string) {
  const summary = (cards as any).__summary;
  return intNum(summary?.[key]);
}

function sum(values: Array<number | null | undefined>) {
  return values.reduce(
    (acc, value) =>
      acc + (typeof value === "number" && Number.isFinite(value) ? value : 0),
    0,
  );
}

function num(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (
      typeof value === "string" &&
      value.trim() !== "" &&
      Number.isFinite(Number(value))
    )
      return Number(value);
  }
  return null;
}

function firstPositive(
  ...values: Array<number | null | undefined>
): number | null {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      return value;
    }
  }
  return null;
}

function intNum(...values: unknown[]): number {
  const value = num(...values);
  return value == null ? 0 : Math.round(value);
}

function text(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function periodFromObject(
  ...sources: Array<Record<string, any> | null | undefined>
): DateRangeValue | null {
  for (const source of sources) {
    if (!source) continue;
    const from = text(
      source.date_from,
      source.period_from,
      source.from,
      source.start_date,
    );
    const to = text(
      source.date_to,
      source.period_to,
      source.to,
      source.end_date,
    );
    if (from && to) return { from, to };
  }
  return null;
}

function money(value: number | null | undefined) {
  return value == null ? "—" : formatMoney(value);
}

function expenseSignedMoney(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  return value < 0
    ? `+${formatMoney(Math.abs(value))}`
    : formatMoney(-Math.abs(value));
}

function compareValue(
  current: number | null | undefined,
  previous: number | null | undefined,
  inverse = false,
): ComparisonValue {
  if (
    current == null ||
    previous == null ||
    !Number.isFinite(current) ||
    !Number.isFinite(previous)
  ) {
    return {
      label: "нет базы для сравнения",
      tone: "neutral",
      diff: null,
      percent: null,
    };
  }
  const diff = current - previous;
  const percent =
    previous === 0 ? null : (diff / Math.max(1, Math.abs(previous))) * 100;
  const isGood = inverse ? diff <= 0 : diff >= 0;
  const sign = diff > 0 ? "+" : diff < 0 ? "−" : "";
  const absPercent = percent == null ? null : Math.abs(percent);
  const label =
    absPercent == null
      ? `${sign}${formatMoneyCompact(Math.abs(diff))} к предыдущему периоду`
      : `${sign}${absPercent.toFixed(1)}% к предыдущему периоду`;
  return {
    label,
    tone: diff === 0 ? "neutral" : isGood ? "good" : "danger",
    diff,
    percent,
  };
}

function formatRange(from: string, to: string) {
  return `${formatShortDate(from)} — ${formatShortDate(to)}`;
}

function formatShortDate(iso: string) {
  try {
    return new Date(`${iso}T00:00:00`).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
    });
  } catch {
    return iso;
  }
}

function previousPeriod(range: DateRangeValue): DateRangeValue {
  const days = daysInclusive(range);
  return {
    from: addDaysIso(range.from, -days),
    to: addDaysIso(range.from, -1),
  };
}

function daysInclusive(range: DateRangeValue): number {
  const from = parseIsoDate(range.from).getTime();
  const to = parseIsoDate(range.to).getTime();
  const diff = Math.max(0, to - from);
  return Math.floor(diff / 86_400_000) + 1;
}

function addDaysIso(iso: string, days: number): string {
  const date = parseIsoDate(iso);
  date.setDate(date.getDate() + days);
  return toIsoDate(date);
}

function parseIsoDate(iso: string): Date {
  return new Date(`${iso}T00:00:00`);
}

function toIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function compactAxis(value: unknown) {
  const n = num(value) ?? 0;
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${Math.round(n / 1_000_000)}M`;
  if (abs >= 1_000) return `${Math.round(n / 1_000)}k`;
  return formatNumber(n);
}

function trustLabel(value: string | null | undefined) {
  const v = String(value ?? "").toLowerCase();
  if (v === "final" || v === "trusted" || v === "business_trusted")
    return "Доверенные";
  if (v.includes("block")) return "Заблокировано";
  if (v.includes("provisional") || v.includes("prelim"))
    return "Предварительно";
  if (v === "test_only") return "Тестовые";
  if (v === "unknown") return "Неизвестно";
  return v ? v.replace(/_/g, " ") : "Неизвестно";
}

function actionCategoryLabel(category: unknown) {
  const value = String(category ?? "").toLowerCase();
  const labels: Record<string, string> = {
    release_cash: "Освободить деньги",
    protect_revenue: "Защитить выручку",
    save_money: "Снизить расходы",
    data_fix: "Исправить данные",
    fix_data: "Исправить данные",
    pricing: "Цена",
    ads: "Реклама",
    stock: "Остатки",
    cost: "Себестоимость",
  };
  return (labels[value] ?? value.replace(/_/g, " ")) || "Категория";
}

function priorityLabel(priority: string) {
  if (priority === "critical") return "Критично";
  if (priority === "high") return "Высокий";
  if (priority === "medium") return "Средний";
  if (priority === "low") return "Низкий";
  return "Приоритет";
}

function priorityClass(priority: string) {
  if (priority === "critical")
    return "border-destructive/40 bg-destructive/10 text-destructive";
  if (priority === "high")
    return "border-warning/40 bg-warning/10 text-warning";
  if (priority === "medium") return "border-info/40 bg-info/10 text-info";
  return "border-muted text-muted-foreground";
}

function toneClasses(tone: MetricTone) {
  switch (tone) {
    case "good":
      return {
        border: "border-l-success",
        badge: "border-success/30 bg-success/10 text-success",
        soft: "border-success/30 bg-success/10 text-success",
      };
    case "warning":
      return {
        border: "border-l-warning",
        badge: "border-warning/30 bg-warning/10 text-warning",
        soft: "border-warning/30 bg-warning/10 text-warning",
      };
    case "danger":
      return {
        border: "border-l-destructive",
        badge: "border-destructive/30 bg-destructive/10 text-destructive",
        soft: "border-destructive/30 bg-destructive/10 text-destructive",
      };
    case "info":
      return {
        border: "border-l-info",
        badge: "border-info/30 bg-info/10 text-info",
        soft: "border-info/30 bg-info/10 text-info",
      };
    default:
      return {
        border: "border-l-border",
        badge: "border-muted bg-muted/40 text-muted-foreground",
        soft: "border-border bg-muted/30 text-muted-foreground",
      };
  }
}
