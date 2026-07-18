import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownRight,
  BadgeCheck,
  Banknote,
  BarChart3,
  Calculator,
  Calendar,
  ChevronRight,
  CircleDollarSign,
  Clock,
  Database,
  FileText,
  Hash,
  Layers,
  ListFilter,
  Megaphone,
  Package,
  Percent,
  ReceiptText,
  RefreshCcw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Truck,
  WalletCards,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  Pie,
  PieChart,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { ApiErrorState } from "@/components/money-ui/ApiErrorState";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";
import { formatMoneyCompact, formatNumber } from "@/lib/format";
import {
  categoryLabel,
  expensesBreakdownQueryOptions,
  expensesLogisticsQueryOptions,
  expensesReportRowsQueryOptions,
  formatMoneyRu,
  formatPercent,
  profitCascadeQueryOptions,
  type BreakdownItem,
  type BreakdownResponse,
  type ExpenseReportRow,
  type LogisticsResponse,
  type ProfitCascadeResponse,
} from "@/lib/queries/expenses";
import { moneySummaryQueryOptions } from "@/lib/queries/money-summary";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_authenticated/expenses")({
  component: ExpensesPage,
  validateSearch: (search: Record<string, unknown>) => ({
    category: typeof search.category === "string" ? search.category : undefined,
    date_from:
      typeof search.date_from === "string" ? search.date_from : undefined,
    date_to: typeof search.date_to === "string" ? search.date_to : undefined,
  }),
});

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

type AttentionItem = {
  tone: Tone;
  icon: LucideIcon;
  title: string;
  value: string;
  detail: string;
};

type ExpenseChartPoint = {
  name: string;
  amount: number;
  color?: string;
  label?: string;
};

type ExpenseReportRowsResult =
  | ExpenseReportRow[]
  | { items: ExpenseReportRow[]; total?: number };

type DrillTarget = {
  key: string;
  label: string;
  category?: string;
  skuId?: number | null;
  nmId?: number | null;
};

type ExpenseDashboardModel = {
  revenue: number | null;
  netProfit: number | null;
  marginPercent: number | null;
  totalExpenses: number | null;
  totalWbExpenses: number | null;
  totalSellerExpenses: number | null;
  totalAdExpenses: number | null;
  logisticsTotal: number | null;
  logisticsSharePercent: number | null;
  expenseLoadPercent: number | null;
  adLoadPercent: number | null;
  sellerLoadPercent: number | null;
  wbLoadPercent: number | null;
  financialFinal: boolean;
  trustState: string | null;
  confidence: string | null;
  sourceOfTruth: string | null;
  financeMismatchPercent: number | null;
  financeMismatchAmount: number | null;
  blockingIssues: number | null;
  openIssues: number | null;
  unallocatedExpenses: number | null;
  unallocatedPercent: number | null;
  negativeCommissionAmount: number | null;
  categoryCount: number;
  finalCategoryCount: number;
  provisionalCategoryCount: number;
  totalRows: number | null;
  largestCategory: BreakdownItem | null;
  items: BreakdownItem[];
  attention: AttentionItem[];
};

function ExpensesPage() {
  const { activeId } = useAccounts();
  const { from, to } = useDateRange();

  const summaryQ = useQuery(
    moneySummaryQueryOptions({
      accountId: activeId,
      dateFrom: from,
      dateTo: to,
    }),
  );
  const breakdown = useQuery(
    expensesBreakdownQueryOptions({
      accountId: activeId,
      dateFrom: from,
      dateTo: to,
    }),
  );
  const logistics = useQuery(
    expensesLogisticsQueryOptions({
      accountId: activeId,
      dateFrom: from,
      dateTo: to,
    }),
  );
  const cascade = useQuery(
    profitCascadeQueryOptions({
      accountId: activeId,
      dateFrom: from,
      dateTo: to,
    }),
  );
  const byCard = useQuery(
    expensesBreakdownQueryOptions({
      accountId: activeId,
      dateFrom: from,
      dateTo: to,
      groupBy: "sku",
    }),
  );
  const byDay = useQuery(
    expensesBreakdownQueryOptions({
      accountId: activeId,
      dateFrom: from,
      dateTo: to,
      groupBy: "day",
    }),
  );
  const bySource = useQuery(
    expensesBreakdownQueryOptions({
      accountId: activeId,
      dateFrom: from,
      dateTo: to,
      groupBy: "source",
    }),
  );

  const summaryBreakdown = useMemo(
    () => summaryToBreakdown(summaryQ.data),
    [summaryQ.data],
  );
  const effective = breakdown.data ?? summaryBreakdown;
  const usingSummaryFallback =
    !breakdown.data && !!summaryBreakdown && breakdown.isFetching;

  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!breakdown.isFetching) {
      setSlow(false);
      return;
    }
    const timer = window.setTimeout(() => setSlow(true), 8000);
    return () => window.clearTimeout(timer);
  }, [breakdown.isFetching]);

  const model = useMemo(
    () =>
      buildDashboardModel({
        breakdown: effective,
        summary: summaryQ.data,
        logistics: logistics.data,
        cascade: cascade.data,
      }),
    [effective, summaryQ.data, logistics.data, cascade.data],
  );

  const [drillCategory, setDrillCategory] = useState<DrillTarget | null>(null);
  const search = Route.useSearch();
  useEffect(() => {
    if (search.category && !drillCategory) {
      setDrillCategory({
        key: search.category,
        label: categoryLabel(search.category),
        category: search.category,
      });
    }
  }, [drillCategory, search.category]);

  const initialLoading =
    !effective && (summaryQ.isLoading || breakdown.isLoading);
  const breakdownError =
    !effective && breakdown.error ? (breakdown.error as Error) : null;

  const refreshAll = () => {
    void summaryQ.refetch();
    void breakdown.refetch();
    void logistics.refetch();
    void cascade.refetch();
  };

  return (
    <PageShell>
      <PageHeader
        title="Расходы"
        description={
          <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>
              {from} - {to}
            </span>
            <span className="text-muted-foreground/70">
              магазин {activeId ?? "-"}
            </span>
          </span>
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={refreshAll}
            disabled={summaryQ.isFetching || breakdown.isFetching}
          >
            <RefreshCcw
              className={cn(
                "mr-2 h-4 w-4",
                (summaryQ.isFetching || breakdown.isFetching) && "animate-spin",
              )}
            />
            Обновить
          </Button>
        }
      />

      <div className="space-y-5">
        <DataDependencyNotice
          accountId={activeId}
          domains={["finance", "sales", "ads"]}
        />

        {(usingSummaryFallback || slow) && (
          <Alert className="border-amber-500/40 bg-amber-500/10 text-amber-950 dark:text-amber-100">
            <Clock className="h-4 w-4" />
            <AlertTitle>Полная детализация еще догружается</AlertTitle>
            <AlertDescription>
              Сейчас показан быстрый срез. Реестр расходов обновится
              автоматически после полной детализации.
            </AlertDescription>
          </Alert>
        )}

        {breakdownError ? (
          <ApiErrorState
            error={breakdownError}
            endpoint="/money/expenses/breakdown"
            onRetry={() => breakdown.refetch()}
          />
        ) : (
          <>
            <AccountingClosePanel model={model} loading={initialLoading} />

            <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
              <RubleTraceBoard model={model} loading={initialLoading} />
              <div className="space-y-4">
                <AttentionQueue
                  items={model.attention}
                  loading={initialLoading}
                />
                <ExpenseFlowPanel
                  model={model}
                  bySource={bySource.data}
                  byDay={byDay.data}
                  loading={
                    initialLoading || bySource.isLoading || byDay.isLoading
                  }
                />
              </div>
            </div>

            <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(420px,0.85fr)]">
              <CardExpenseLeaders
                data={byCard.data}
                loading={byCard.isLoading}
                onOpen={(item) =>
                  setDrillCategory({
                    key:
                      item.sku_id != null
                        ? `sku:${item.sku_id}`
                        : "sku:unallocated",
                    label: cardLabel(item),
                    skuId: item.sku_id,
                    nmId: item.nm_id,
                  })
                }
              />
              <div className="space-y-4">
                <ExpenseCausePanel
                  model={model}
                  logistics={logistics.data}
                  loading={initialLoading || logistics.isLoading}
                  onOpenCategory={(category, label) =>
                    setDrillCategory({ key: category, label, category })
                  }
                />
                <CardConcentrationPanel
                  data={byCard.data}
                  loading={byCard.isLoading}
                />
              </div>
            </div>

            <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(380px,0.78fr)]">
              <ExpenseRegister
                items={model.items}
                total={model.totalExpenses}
                loading={initialLoading}
                onDrill={(cat, label) =>
                  setDrillCategory({ key: cat, label, category: cat })
                }
              />
              <LogisticsControlPanel
                data={logistics.data}
                loading={logistics.isLoading}
                error={logistics.error as Error | null}
                fallbackTotal={model.logisticsTotal}
                fallbackShare={model.logisticsSharePercent}
                onDrill={(cat, label) =>
                  setDrillCategory({ key: cat, label, category: cat })
                }
              />
            </div>
          </>
        )}
      </div>

      <ReportRowsDrawer
        open={!!drillCategory}
        category={drillCategory}
        onClose={() => setDrillCategory(null)}
        accountId={activeId}
        dateFrom={from}
        dateTo={to}
      />
    </PageShell>
  );
}

function RubleTraceBoard({
  model,
  loading,
}: {
  model: ExpenseDashboardModel;
  loading: boolean;
}) {
  const positiveItems = useMemo(
    () =>
      model.items
        .filter((item) => (item.amount ?? 0) > 0)
        .sort((a, b) => (b.amount ?? 0) - (a.amount ?? 0))
        .slice(0, 7),
    [model.items],
  );
  const total = positive(model.totalExpenses) || 1;
  const largest = positiveItems[0];
  const largestShare = largest ? positive(largest.amount) / total : null;
  const revenueBase = positive(model.revenue);
  const expenseFromRevenue =
    revenueBase > 0 ? positive(model.totalExpenses) / revenueBase : null;
  const profitFromRevenue =
    revenueBase > 0 && model.netProfit != null
      ? model.netProfit / revenueBase
      : null;
  const wbFromRevenue =
    revenueBase > 0 ? positive(model.totalWbExpenses) / revenueBase : null;
  const adFromRevenue =
    revenueBase > 0 ? positive(model.totalAdExpenses) / revenueBase : null;
  const expenseLoadPercent =
    expenseFromRevenue == null ? null : expenseFromRevenue * 100;
  const profitLoadPercent =
    profitFromRevenue == null ? null : profitFromRevenue * 100;
  const wbLoadPercent = wbFromRevenue == null ? null : wbFromRevenue * 100;
  const adLoadPercent = adFromRevenue == null ? null : adFromRevenue * 100;
  return (
    <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="grid gap-4 p-4 2xl:grid-cols-[minmax(360px,1fr)_minmax(520px,0.95fr)] 2xl:items-end">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="bg-zinc-50 text-zinc-700">
                Аудит расходов
              </Badge>
              <FinalityBadge final={model.financialFinal} />
              {model.sourceOfTruth && (
                <Badge variant="secondary" className="font-normal">
                  {sourceLabel(model.sourceOfTruth)}
                </Badge>
              )}
            </div>
            <h2 className="mt-3 max-w-[720px] text-2xl font-semibold leading-tight tracking-normal text-zinc-950 dark:text-zinc-50">
              Куда ушел каждый рубль
            </h2>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-zinc-500">
              <span className="rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 dark:border-zinc-800 dark:bg-zinc-900">
                {largest
                  ? `Главная статья: ${categoryLabel(largest.category, largest.category_label ?? largest.label)}`
                  : "Главная статья пока не найдена"}
              </span>
              <span className="rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 dark:border-zinc-800 dark:bg-zinc-900">
                {largestShare == null
                  ? "Доля не рассчитана"
                  : `${formatKopeks(largestShare)} из каждого рубля`}
              </span>
            </div>
          </div>

          <div className="grid gap-3 xl:grid-cols-[220px_minmax(0,1fr)]">
            <ExpensePressureDial
              loading={loading}
              expensePercent={expenseLoadPercent}
              profitPercent={profitLoadPercent}
              wbPercent={wbLoadPercent}
              adPercent={adLoadPercent}
            />
            <div className="grid grid-cols-2 gap-2">
              <CompactFigure
                label="Расходы в 1 ₽"
                value={formatRublePart(expenseFromRevenue)}
                loading={loading}
                tone={
                  (expenseFromRevenue ?? 0) > 0.7
                    ? "warning"
                    : ("neutral" as Tone)
                }
              />
              <CompactFigure
                label="Прибыль в 1 ₽"
                value={formatRublePart(profitFromRevenue)}
                loading={loading}
                tone={
                  (profitFromRevenue ?? 0) < 0 ? "danger" : ("success" as Tone)
                }
              />
              <CompactFigure
                label="WB нагрузка"
                value={formatRublePart(wbFromRevenue)}
                loading={loading}
                tone="warning"
              />
              <CompactFigure
                label="Реклама"
                value={formatRublePart(adFromRevenue)}
                loading={loading}
                tone={
                  (adFromRevenue ?? 0) > 0.18 ? "warning" : ("info" as Tone)
                }
              />
            </div>
          </div>
        </div>
        <div className="grid h-1 grid-cols-[1.2fr_1fr_0.75fr_0.55fr]">
          <div className="bg-emerald-500" />
          <div className="bg-sky-500" />
          <div className="bg-amber-500" />
          <div className="bg-red-500" />
        </div>
      </div>

      <div className="space-y-4 p-4">
        <div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="text-xs font-semibold uppercase tracking-normal text-zinc-500">
                Карта 1 ₽ расходов
              </div>
              <div className="mt-1 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                Копейки показывают реальную долю статьи в расходах
              </div>
            </div>
            <div className="text-xs text-zinc-500">
              Строки открываются из реестра и карточек ниже
            </div>
          </div>

          <ExpenseRubleRibbon
            items={positiveItems}
            total={total}
            loading={loading}
          />

          <div className="mt-4 space-y-3">
            {loading
              ? Array.from({ length: 6 }).map((_, idx) => (
                  <Skeleton key={idx} className="h-12 w-full rounded-md" />
                ))
              : positiveItems.map((item, idx) => {
                  const amount = positive(item.amount);
                  const share = amount / total;
                  const accent = expenseAccent(idx);
                  return (
                    <div
                      key={item.category}
                      className="rounded-md border border-zinc-200 bg-zinc-50/60 p-3 dark:border-zinc-800 dark:bg-zinc-900/50"
                    >
                      <div className="grid gap-2 sm:grid-cols-[minmax(180px,0.9fr)_minmax(180px,1.4fr)_96px_120px] sm:items-center">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span
                              className={cn(
                                "h-2.5 w-2.5 rounded-full",
                                accent.dot,
                              )}
                            />
                            <span className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                              {categoryLabel(
                                item.category,
                                item.category_label ?? item.label,
                              )}
                            </span>
                          </div>
                          <div className="mt-1 truncate text-[11px] text-zinc-500">
                            {sourceShortLabel(item.source)}
                          </div>
                        </div>
                        <div className="h-2.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                          <div
                            className={cn("h-full rounded-full", accent.bar)}
                            style={{
                              width: `${clamp(share * 100, 2, 100)}%`,
                            }}
                          />
                        </div>
                        <div
                          className={cn(
                            "rounded-full px-2.5 py-1 text-center text-xs font-semibold tabular-nums",
                            accent.chip,
                          )}
                        >
                          {formatKopeks(share)}
                        </div>
                        <div className="text-right text-sm font-semibold tabular-nums text-zinc-900 dark:text-zinc-100">
                          {formatMoneyRu(amount)}
                        </div>
                      </div>
                    </div>
                  );
                })}
          </div>
        </div>
      </div>
    </section>
  );
}

function ExpenseFlowPanel({
  model,
  bySource,
  byDay,
  loading,
}: {
  model: ExpenseDashboardModel;
  bySource: BreakdownResponse | undefined;
  byDay: BreakdownResponse | undefined;
  loading: boolean;
}) {
  const dayItems = (byDay?.items ?? [])
    .filter((item) => Math.abs(item.amount ?? 0) > 0)
    .sort((a, b) =>
      String(a.stat_date ?? a.group_key ?? "").localeCompare(
        String(b.stat_date ?? b.group_key ?? ""),
      ),
    )
    .slice(-10);
  let cumulative = 0;
  const flowData = dayItems.map((item) => {
    const amount = Math.abs(item.amount ?? 0);
    cumulative += amount;
    return {
      name: shortDate(item.stat_date ?? item.group_key),
      label: String(item.stat_date ?? item.group_key ?? ""),
      amount,
      cumulative,
      color: "#0891b2",
    };
  });
  const sourceItems = (bySource?.items ?? [])
    .filter((item) => Math.abs(item.amount ?? 0) > 0)
    .sort((a, b) => Math.abs(b.amount ?? 0) - Math.abs(a.amount ?? 0))
    .slice(0, 4);
  const sourceChartItems: ExpenseChartPoint[] = sourceItems.map(
    (item, idx) => ({
      name: sourceShortLabel(item.source ?? item.group_key ?? item.label),
      amount: Math.abs(item.amount ?? 0),
      color: expenseHex(idx + 1),
    }),
  );
  const total = flowData.reduce((sum, item) => sum + item.amount, 0);
  const avg = flowData.length ? total / flowData.length : null;
  const peak = flowData.reduce<(typeof flowData)[number] | null>(
    (best, item) => (!best || item.amount > best.amount ? item : best),
    null,
  );

  return (
    <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 bg-zinc-50 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-base font-semibold text-zinc-950 dark:text-zinc-50">
            <BarChart3 className="h-4 w-4 text-cyan-700 dark:text-cyan-300" />
            Пульс расходов
          </div>
          <Badge variant="outline" className="bg-white text-xs font-normal">
            {flowData.length || "—"} дн.
          </Badge>
        </div>
      </div>

      <div className="grid border-b border-zinc-200 sm:grid-cols-3 dark:border-zinc-800">
        <MiniStat
          label="за период"
          value={formatMoneyRu(model.totalExpenses)}
          loading={loading}
        />
        <MiniStat
          label="средний день"
          value={formatMoneyRu(avg)}
          loading={loading}
        />
        <MiniStat
          label={peak ? `пик ${peak.name}` : "пик"}
          value={peak ? formatMoneyRu(peak.amount) : "—"}
          loading={loading}
        />
      </div>

      <div className="p-4">
        {loading ? (
          <Skeleton className="h-[190px] w-full rounded-md" />
        ) : flowData.length === 0 ? (
          <div className="flex h-[190px] items-center justify-center text-sm text-muted-foreground">
            Нет дневной динамики
          </div>
        ) : (
          <div className="h-[190px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={flowData}
                margin={{ top: 12, right: 8, left: 0, bottom: 0 }}
              >
                <defs>
                  <linearGradient
                    id="expense-flow-line"
                    x1="0"
                    x2="0"
                    y1="0"
                    y2="1"
                  >
                    <stop offset="5%" stopColor="#059669" stopOpacity={0.22} />
                    <stop offset="95%" stopColor="#059669" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  vertical={false}
                  stroke="rgba(148,163,184,0.22)"
                />
                <XAxis
                  dataKey="name"
                  tickLine={false}
                  axisLine={false}
                  minTickGap={14}
                  tick={{ fontSize: 10, fill: "#71717a" }}
                />
                <YAxis
                  tickFormatter={(value) => formatMoneyCompact(Number(value))}
                  tickLine={false}
                  axisLine={false}
                  width={54}
                  tick={{ fontSize: 10, fill: "#71717a" }}
                />
                <Tooltip content={<ExpenseChartTooltip />} />
                <Bar
                  dataKey="amount"
                  name="день"
                  fill="#0891b2"
                  radius={[4, 4, 0, 0]}
                  barSize={18}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="cumulative"
                  name="накоплено"
                  stroke="#059669"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="mt-4 grid gap-3 2xl:grid-cols-[150px_minmax(0,1fr)] 2xl:items-center">
          <ExpenseSourceDonut
            data={sourceChartItems}
            loading={loading || !bySource}
          />
          <div className="space-y-1.5">
            {loading || !bySource ? (
              Array.from({ length: 4 }).map((_, idx) => (
                <Skeleton key={idx} className="h-8 w-full rounded-md" />
              ))
            ) : sourceItems.length === 0 ? (
              <div className="text-sm text-muted-foreground">
                Нет источников
              </div>
            ) : (
              sourceItems.map((item, idx) => {
                const amount = Math.abs(item.amount ?? 0);
                const share =
                  model.totalExpenses && model.totalExpenses !== 0
                    ? amount / Math.abs(model.totalExpenses)
                    : null;
                return (
                  <div
                    key={item.group_key ?? item.source ?? item.label}
                    className="grid grid-cols-[minmax(0,1fr)_92px] items-center gap-3 border-b border-zinc-100 py-1.5 text-sm last:border-b-0 dark:border-zinc-800"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ background: expenseHex(idx + 1) }}
                      />
                      <span className="truncate text-zinc-600 dark:text-zinc-300">
                        {sourceShortLabel(
                          item.source ?? item.group_key ?? item.label,
                        )}
                      </span>
                    </span>
                    <span className="text-right text-xs font-semibold tabular-nums text-zinc-950 dark:text-zinc-50">
                      {share == null ? "—" : formatKopeks(share)}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function MiniStat({
  label,
  value,
  loading,
}: {
  label: string;
  value: string;
  loading: boolean;
}) {
  return (
    <div className="min-w-0 border-b border-zinc-200 px-4 py-3 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0 dark:border-zinc-800">
      <div className="text-[11px] text-zinc-500">{label}</div>
      {loading ? (
        <Skeleton className="mt-2 h-5 w-24" />
      ) : (
        <div className="mt-1 truncate text-sm font-semibold tabular-nums text-zinc-950 dark:text-zinc-50">
          {value}
        </div>
      )}
    </div>
  );
}

function ExpenseRubleRibbon({
  items,
  total,
  loading,
}: {
  items: BreakdownItem[];
  total: number;
  loading: boolean;
}) {
  if (loading) {
    return <Skeleton className="mt-4 h-10 w-full rounded-full" />;
  }

  const slices = items
    .filter((item) => positive(item.amount) > 0)
    .slice(0, 7)
    .map((item, idx) => {
      const amount = positive(item.amount);
      return {
        key: item.category,
        label: categoryLabel(item.category, item.category_label ?? item.label),
        amount,
        share: amount / Math.max(total, 1),
        color: expenseHex(idx),
      };
    });

  if (slices.length === 0) return null;

  return (
    <div className="mt-4">
      <div className="flex h-4 overflow-hidden rounded-full bg-zinc-100 ring-1 ring-inset ring-zinc-200 dark:bg-zinc-900 dark:ring-zinc-800">
        {slices.map((slice) => (
          <div
            key={slice.key}
            className="h-full transition-all"
            style={{
              background: slice.color,
              flex: `${clamp(slice.share, 0.012, 1)} 1 0%`,
            }}
            title={`${slice.label}: ${formatMoneyRu(slice.amount)} (${formatKopeks(slice.share)})`}
          />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-zinc-500">
        {slices.slice(0, 4).map((slice) => (
          <span
            key={slice.key}
            className="inline-flex min-w-0 items-center gap-1.5"
          >
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: slice.color }}
            />
            <span className="max-w-[170px] truncate">{slice.label}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function ExpensePressureDial({
  loading,
  expensePercent,
  profitPercent,
  wbPercent,
  adPercent,
}: {
  loading: boolean;
  expensePercent: number | null;
  profitPercent: number | null;
  wbPercent: number | null;
  adPercent: number | null;
}) {
  const tone = expensePressureTone(expensePercent);
  const ringData: ExpenseChartPoint[] = [
    {
      name: "Расходы",
      amount: normalizeChartPercent(expensePercent),
      color: toneHex(tone),
    },
    {
      name: "Вайлдберриз",
      amount: normalizeChartPercent(wbPercent),
      color: "#0891b2",
    },
    {
      name: "Реклама",
      amount: normalizeChartPercent(adPercent),
      color: "#6366f1",
    },
  ];

  return (
    <div className="min-h-[156px] overflow-hidden rounded-md border border-zinc-200 bg-zinc-50/80 p-3 dark:border-zinc-800 dark:bg-zinc-900/50">
      {loading ? (
        <Skeleton className="h-[132px] w-full rounded-md" />
      ) : (
        <>
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-[11px] font-medium uppercase tracking-normal text-zinc-500">
                Нагрузка
              </div>
              <div className="mt-0.5 text-[11px] text-zinc-500">
                расходы / выручка
              </div>
            </div>
            <div className={cn("text-sm font-semibold", toneTextClass(tone))}>
              {formatPercent(expensePercent)}
            </div>
          </div>

          <div className="relative mx-auto mt-1 h-[88px] w-[152px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                data={ringData}
                innerRadius="50%"
                outerRadius="98%"
                startAngle={210}
                endAngle={-30}
                barSize={8}
              >
                <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
                <RadialBar
                  dataKey="amount"
                  background={{ fill: "rgba(148, 163, 184, 0.16)" }}
                  cornerRadius={999}
                  isAnimationActive={false}
                >
                  {ringData.map((point) => (
                    <Cell key={point.name} fill={point.color} />
                  ))}
                </RadialBar>
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center pt-2">
              <span
                className={cn(
                  "text-xl font-semibold tabular-nums",
                  toneTextClass(tone),
                )}
              >
                {formatPercent(expensePercent, 1)}
              </span>
            </div>
          </div>

          <div className="mt-1 grid grid-cols-3 gap-1 text-[10px] leading-tight text-zinc-500">
            <span className="truncate">WB {formatPercent(wbPercent, 1)}</span>
            <span className="truncate">
              реклама {formatPercent(adPercent, 1)}
            </span>
            <span
              className={cn(
                "truncate font-medium",
                (profitPercent ?? 0) < 0
                  ? toneTextClass("danger")
                  : toneTextClass("success"),
              )}
            >
              прибыль {formatPercent(profitPercent, 1)}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

function ExpenseSourceDonut({
  data,
  loading,
  centerLabel = "источники",
  centerValue,
}: {
  data: ExpenseChartPoint[];
  loading: boolean;
  centerLabel?: string;
  centerValue?: string;
}) {
  const total = data.reduce((sum, item) => sum + item.amount, 0);

  if (loading) {
    return <Skeleton className="h-[150px] w-full rounded-full" />;
  }

  if (data.length === 0 || total <= 0) {
    return (
      <div className="flex h-[150px] items-center justify-center rounded-full border border-dashed border-zinc-300 text-xs text-zinc-500 dark:border-zinc-700">
        Нет данных
      </div>
    );
  }

  return (
    <div className="relative h-[150px] min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Tooltip content={<ExpenseChartTooltip />} />
          <Pie
            data={data}
            dataKey="amount"
            nameKey="name"
            innerRadius={42}
            outerRadius={67}
            paddingAngle={2}
            stroke="transparent"
            isAnimationActive={false}
          >
            {data.map((point) => (
              <Cell key={point.name} fill={point.color} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
        <div className="text-[10px] uppercase tracking-normal text-zinc-500">
          {centerLabel}
        </div>
        <div className="mt-1 max-w-[112px] truncate text-sm font-semibold tabular-nums text-zinc-950 dark:text-zinc-50">
          {centerValue ?? formatMoneyRu(total)}
        </div>
      </div>
    </div>
  );
}

function ExpenseAreaSparkline({
  data,
  loading,
}: {
  data: ExpenseChartPoint[];
  loading: boolean;
}) {
  if (loading) {
    return <Skeleton className="mt-3 h-28 w-full rounded-md" />;
  }

  if (data.length === 0) {
    return (
      <div className="mt-3 flex h-28 items-center justify-center text-sm text-muted-foreground">
        Нет дневных данных
      </div>
    );
  }

  return (
    <div className="mt-3 h-28">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 8, right: 6, left: 6, bottom: 0 }}
        >
          <defs>
            <linearGradient id="expense-days-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="5%" stopColor="#0891b2" stopOpacity={0.34} />
              <stop offset="95%" stopColor="#0891b2" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="name"
            tickLine={false}
            axisLine={false}
            tickMargin={6}
            minTickGap={14}
            tick={{ fontSize: 10, fill: "#71717a" }}
          />
          <Tooltip content={<ExpenseChartTooltip />} />
          <Area
            type="monotone"
            dataKey="amount"
            name="Расходы"
            stroke="#0891b2"
            strokeWidth={2.5}
            fill="url(#expense-days-fill)"
            fillOpacity={1}
            dot={false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function ExpenseChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{
    color?: string;
    name?: string | number;
    payload?: ExpenseChartPoint;
    value?: number | string;
  }>;
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  const title =
    payload[0]?.payload?.label || payload[0]?.payload?.name || String(label);

  return (
    <div className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-1 max-w-[220px] truncate font-medium text-zinc-500">
        {title}
      </div>
      {payload.map((entry, idx) => (
        <div
          key={`${entry.name ?? "value"}-${idx}`}
          className="flex items-center justify-between gap-4"
        >
          <span className="flex min-w-0 items-center gap-2 text-zinc-600 dark:text-zinc-300">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: entry.color ?? entry.payload?.color }}
            />
            <span className="truncate">
              {entry.name ?? entry.payload?.name ?? "Сумма"}
            </span>
          </span>
          <span className="font-semibold tabular-nums text-zinc-950 dark:text-zinc-50">
            {formatMoneyRu(firstNumber(entry.value))}
          </span>
        </div>
      ))}
    </div>
  );
}

function HeroMetric({
  label,
  value,
  loading,
  accent,
}: {
  label: string;
  value: string;
  loading: boolean;
  accent: "emerald" | "cyan" | "amber" | "rose";
}) {
  const accents: Record<typeof accent, string> = {
    emerald: "border-emerald-400/30 text-emerald-100",
    cyan: "border-cyan-400/30 text-cyan-100",
    amber: "border-amber-400/30 text-amber-100",
    rose: "border-rose-400/30 text-rose-100",
  };
  return (
    <div
      className={cn("rounded-lg border bg-white/[0.08] p-3", accents[accent])}
    >
      <div className="text-[11px] text-zinc-300">{label}</div>
      {loading ? (
        <Skeleton className="mt-2 h-5 w-20 bg-white/20" />
      ) : (
        <div className="mt-1 truncate text-base font-semibold tabular-nums text-white">
          {value}
        </div>
      )}
    </div>
  );
}

function CardExpenseLeaders({
  data,
  loading,
  onOpen,
}: {
  data: BreakdownResponse | undefined;
  loading: boolean;
  onOpen: (item: BreakdownItem) => void;
}) {
  const rows = (data?.items ?? [])
    .filter((item) => Math.abs(item.amount ?? 0) > 0)
    .sort((a, b) => Math.abs(b.amount ?? 0) - Math.abs(a.amount ?? 0))
    .slice(0, 12);
  const max = Math.max(...rows.map((item) => Math.abs(item.amount ?? 0)), 1);

  return (
    <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-start justify-between gap-3 border-b border-zinc-200 bg-zinc-50 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
        <div>
          <div className="flex items-center gap-2 text-base font-semibold text-zinc-950 dark:text-zinc-50">
            <Package className="h-4 w-4 text-emerald-600" />
            Карточки, куда ушло больше всего
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            Нажмите на строку, чтобы открыть расходные операции именно по этой
            карточке.
          </div>
        </div>
      </div>
      <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
        {loading ? (
          Array.from({ length: 8 }).map((_, idx) => (
            <Skeleton key={idx} className="m-3 h-14 rounded-md" />
          ))
        ) : rows.length === 0 ? (
          <div className="p-6 text-sm text-zinc-500">
            Нет карточек с расходами
          </div>
        ) : (
          rows.map((item, idx) => {
            const accent = expenseAccent(idx);
            const share = Math.abs(item.amount ?? 0) / max;
            return (
              <button
                key={item.group_key ?? `${item.sku_id}-${item.nm_id}-${idx}`}
                type="button"
                className="grid w-full grid-cols-[42px_minmax(0,1fr)_140px_28px] items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-emerald-50/60 dark:hover:bg-emerald-950/20"
                onClick={() => onOpen(item)}
              >
                <span
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-md text-xs font-bold",
                    accent.chip,
                  )}
                >
                  {idx + 1}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                    {cardLabel(item)}
                  </span>
                  <span className="mt-1 block truncate text-xs text-zinc-500">
                    Артикул Вайлдберриз {item.nm_id ?? "-"} · штрихкод{" "}
                    {item.barcode ?? "-"} · строк{" "}
                    {formatNumber(
                      Number(item.row_count ?? item.rows_count ?? 0) || 0,
                    )}
                  </span>
                  <span className="mt-2 block h-2 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                    <span
                      className={cn("block h-full rounded-full", accent.bar)}
                      style={{
                        width: `${clamp(share * 100, 3, 100)}%`,
                      }}
                    />
                  </span>
                </span>
                <span
                  className={cn(
                    "text-right text-sm font-semibold tabular-nums text-zinc-950 dark:text-zinc-50",
                    (item.amount ?? 0) < 0 && "text-red-700",
                  )}
                >
                  {formatMoneyRu(item.amount)}
                </span>
                <ChevronRight className="h-4 w-4 text-zinc-400" />
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}

function CardConcentrationPanel({
  data,
  loading,
}: {
  data: BreakdownResponse | undefined;
  loading: boolean;
}) {
  const allRows = (data?.items ?? [])
    .filter((item) => Math.abs(item.amount ?? 0) > 0)
    .sort((a, b) => Math.abs(b.amount ?? 0) - Math.abs(a.amount ?? 0));
  const total = allRows.reduce(
    (sum, item) => sum + Math.abs(item.amount ?? 0),
    0,
  );
  const topRows = allRows.slice(0, 6);
  const topThreeTotal = topRows
    .slice(0, 3)
    .reduce((sum, item) => sum + Math.abs(item.amount ?? 0), 0);
  const topThreeShare = total > 0 ? (topThreeTotal / total) * 100 : null;
  const chartData: ExpenseChartPoint[] = topRows.map((item, idx) => ({
    name: cardLabel(item),
    amount: Math.abs(item.amount ?? 0),
    color: expenseHex(idx),
  }));

  return (
    <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 bg-emerald-50/70 px-4 py-3 dark:border-zinc-800 dark:bg-emerald-950/20">
        <div className="flex items-center gap-2 text-base font-semibold text-zinc-950 dark:text-zinc-50">
          <Package className="h-4 w-4 text-emerald-700 dark:text-emerald-300" />
          Концентрация по карточкам
        </div>
        <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
          Быстро показывает, где расход собран в нескольких товарах.
        </div>
      </div>
      <div className="p-4">
        <div className="grid gap-3 2xl:grid-cols-[150px_minmax(0,1fr)] 2xl:items-center">
          <ExpenseSourceDonut
            data={chartData}
            loading={loading}
            centerLabel="топ 3"
            centerValue={formatPercent(topThreeShare, 0)}
          />
          <div className="space-y-2">
            {loading ? (
              Array.from({ length: 5 }).map((_, idx) => (
                <Skeleton key={idx} className="h-9 w-full rounded-md" />
              ))
            ) : topRows.length === 0 ? (
              <div className="text-sm text-muted-foreground">
                Нет расходов по карточкам
              </div>
            ) : (
              topRows.slice(0, 5).map((item, idx) => {
                const amount = Math.abs(item.amount ?? 0);
                const share = total > 0 ? amount / total : 0;
                return (
                  <div
                    key={
                      item.group_key ?? `${item.sku_id}-${item.nm_id}-${idx}`
                    }
                    className="space-y-1.5"
                  >
                    <div className="flex items-center justify-between gap-3 text-sm">
                      <span className="flex min-w-0 items-center gap-2">
                        <span
                          className="h-2.5 w-2.5 shrink-0 rounded-full"
                          style={{ background: expenseHex(idx) }}
                        />
                        <span className="truncate font-medium">
                          {cardLabel(item)}
                        </span>
                      </span>
                      <span className="shrink-0 text-xs font-semibold tabular-nums">
                        {formatKopeks(share)}
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${clamp(share * 100, 2, 100)}%`,
                          background: expenseHex(idx),
                        }}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function ExpenseCausePanel({
  model,
  logistics,
  loading,
  onOpenCategory,
}: {
  model: ExpenseDashboardModel;
  logistics: LogisticsResponse | undefined;
  loading: boolean;
  onOpenCategory: (category: string, label: string) => void;
}) {
  const topCategories = model.items
    .filter((item) => (item.amount ?? 0) > 0)
    .sort((a, b) => (b.amount ?? 0) - (a.amount ?? 0))
    .slice(0, 5);
  const operations = logistics?.by_seller_oper_name ?? [];
  const reportFields = model.items
    .filter(
      (item) =>
        item.category === "wb_commission" ||
        item.category === "payment_processing" ||
        item.category === "penalty" ||
        item.category === "deduction",
    )
    .slice(0, 4);

  return (
    <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 bg-amber-50 px-4 py-3 dark:border-zinc-800 dark:bg-amber-950/20">
        <div className="flex items-center gap-2 text-base font-semibold text-zinc-950 dark:text-zinc-50">
          <ListFilter className="h-4 w-4 text-amber-700 dark:text-amber-300" />
          Почему списались деньги
        </div>
        <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
          Здесь не общий итог, а бухгалтерская причина: статья, операция и поле
          финансового отчета.
        </div>
      </div>
      <div className="grid gap-0 md:grid-cols-2 xl:grid-cols-1">
        <div className="border-b border-zinc-200 p-4 md:border-r xl:border-r-0 dark:border-zinc-800">
          <div className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">
            Самые дорогие статьи
          </div>
          <div className="mt-3 space-y-2">
            {loading
              ? Array.from({ length: 4 }).map((_, idx) => (
                  <Skeleton key={idx} className="h-10 w-full rounded-md" />
                ))
              : topCategories.map((item, idx) => {
                  const accent = expenseAccent(idx);
                  return (
                    <button
                      key={item.category}
                      type="button"
                      className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-left transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800/60"
                      onClick={() =>
                        onOpenCategory(
                          item.category,
                          categoryLabel(
                            item.category,
                            item.category_label ?? item.label,
                          ),
                        )
                      }
                    >
                      <span className="flex items-center justify-between gap-3">
                        <span className="flex min-w-0 items-center gap-2">
                          <span
                            className={cn(
                              "h-2.5 w-2.5 rounded-full",
                              accent.dot,
                            )}
                          />
                          <span className="truncate text-sm font-medium">
                            {categoryLabel(
                              item.category,
                              item.category_label ?? item.label,
                            )}
                          </span>
                        </span>
                        <span className="shrink-0 text-sm font-semibold tabular-nums">
                          {formatMoneyRu(item.amount)}
                        </span>
                      </span>
                    </button>
                  );
                })}
          </div>
        </div>
        <div className="p-4">
          <div className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">
            Операции Вайлдберриз
          </div>
          <div className="mt-3 space-y-2">
            {loading ? (
              Array.from({ length: 4 }).map((_, idx) => (
                <Skeleton key={idx} className="h-10 w-full rounded-md" />
              ))
            ) : operations.length > 0 ? (
              operations.slice(0, 5).map((item, idx) => {
                const accent = expenseAccent(idx + 2);
                return (
                  <div
                    key={item.group_key ?? item.label}
                    className="rounded-md border border-zinc-200 bg-zinc-50/70 px-3 py-2 text-sm dark:border-zinc-800 dark:bg-zinc-900/70"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="flex min-w-0 items-center gap-2">
                        <span
                          className={cn("h-2.5 w-2.5 rounded-full", accent.dot)}
                        />
                        <span className="truncate text-zinc-600 dark:text-zinc-300">
                          {item.label ?? "-"}
                        </span>
                      </span>
                      <span className="font-semibold tabular-nums text-zinc-950 dark:text-zinc-50">
                        {formatMoneyRu(item.amount)}
                      </span>
                    </div>
                  </div>
                );
              })
            ) : reportFields.length > 0 ? (
              reportFields.map((item, idx) => {
                const accent = expenseAccent(idx + 3);
                return (
                  <div
                    key={item.category}
                    className="rounded-md border border-zinc-200 bg-zinc-50/70 px-3 py-2 text-sm dark:border-zinc-800 dark:bg-zinc-900/70"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="flex min-w-0 items-center gap-2">
                        <span
                          className={cn("h-2.5 w-2.5 rounded-full", accent.dot)}
                        />
                        <span className="truncate text-zinc-600 dark:text-zinc-300">
                          {categoryLabel(
                            item.category,
                            item.category_label ?? item.label,
                          )}
                        </span>
                      </span>
                      <span className="font-semibold tabular-nums text-zinc-950 dark:text-zinc-50">
                        {formatMoneyRu(item.amount)}
                      </span>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-sm text-zinc-500">
                Нет разбивки по операциям
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function CompactFigure({
  label,
  value,
  loading,
  tone = "neutral",
}: {
  label: string;
  value: string;
  loading: boolean;
  tone?: Tone;
}) {
  return (
    <div className="rounded-md border bg-background px-3 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      {loading ? (
        <Skeleton className="mt-2 h-5 w-20" />
      ) : (
        <div
          className={cn(
            "mt-1 truncate text-sm font-semibold tabular-nums",
            toneTextClass(tone),
          )}
        >
          {value}
        </div>
      )}
    </div>
  );
}

function AccountingClosePanel({
  model,
  loading,
}: {
  model: ExpenseDashboardModel;
  loading: boolean;
}) {
  const closeTone: Tone = model.financialFinal
    ? "success"
    : model.blockingIssues
      ? "danger"
      : "warning";
  const CloseIcon = model.financialFinal ? ShieldCheck : ShieldAlert;

  const checks = [
    {
      label: "Статус периода",
      value: model.financialFinal ? "Финальный" : "Предварительный",
      detail: model.trustState
        ? trustStateLabel(model.trustState)
        : model.confidence
          ? confidenceLabel(model.confidence)
          : "Проверка источников",
      tone: closeTone,
      icon: CloseIcon,
    },
    {
      label: "Сверка с фин. отчетом",
      value:
        model.financeMismatchPercent == null
          ? "Нет данных"
          : formatPercent(model.financeMismatchPercent, 2),
      detail:
        model.financeMismatchAmount == null
          ? "Ожидается финансовый источник"
          : `Расхождение ${formatMoneyRu(model.financeMismatchAmount)}`,
      tone:
        model.financeMismatchPercent != null &&
        Math.abs(model.financeMismatchPercent) >= 5
          ? "danger"
          : "success",
      icon: Calculator,
    },
    {
      label: "Нераспределенные расходы",
      value: formatMoneyRu(model.unallocatedExpenses),
      detail:
        model.unallocatedPercent == null
          ? "Без оценки доли"
          : `${formatPercent(model.unallocatedPercent)} от выручки`,
      tone: (model.unallocatedExpenses ?? 0) > 0 ? "warning" : "success",
      icon: Database,
    },
    {
      label: "Категории реестра",
      value: formatNumber(model.categoryCount),
      detail: `${formatNumber(model.finalCategoryCount)} финально, ${formatNumber(model.provisionalCategoryCount)} предварительно`,
      tone: model.provisionalCategoryCount > 0 ? "warning" : "success",
      icon: ReceiptText,
    },
  ];

  return (
    <section className="rounded-lg border bg-card">
      <div className="grid gap-0 lg:grid-cols-[minmax(260px,0.9fr)_minmax(0,2.1fr)]">
        <div
          className={cn(
            "flex min-h-[156px] flex-col justify-between border-b p-4 lg:border-b-0 lg:border-r",
            closeTone === "success" && "bg-emerald-500/5",
            closeTone === "warning" && "bg-amber-500/5",
            closeTone === "danger" && "bg-red-500/5",
          )}
        >
          <div className="flex items-start gap-3">
            <div
              className={cn("rounded-md border p-2", toneIconClass(closeTone))}
            >
              <CloseIcon className="h-5 w-5" />
            </div>
            <div>
              <div className="text-xs font-medium uppercase text-muted-foreground">
                Бухгалтерское закрытие
              </div>
              <div className="mt-1 text-lg font-semibold">
                {model.financialFinal
                  ? "Период можно закрывать"
                  : "Период требует контроля"}
              </div>
            </div>
          </div>
          <div className="mt-4 text-sm text-muted-foreground">
            {model.financialFinal
              ? "Финансовый источник подтвержден, сверка не блокирует управленческий отчет."
              : "Перед управленческими выводами проверьте расхождения, распределение и спорные расходы."}
          </div>
        </div>

        <div className="grid gap-0 sm:grid-cols-2 xl:grid-cols-4">
          {checks.map((check) => (
            <div
              key={check.label}
              className="min-w-0 border-b p-4 last:border-b-0 sm:[&:nth-child(odd)]:border-r xl:border-b-0 xl:border-r xl:last:border-r-0"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs text-muted-foreground">
                  {check.label}
                </div>
                <check.icon
                  className={cn("h-4 w-4", toneTextClass(check.tone))}
                />
              </div>
              {loading ? (
                <Skeleton className="mt-3 h-7 w-28" />
              ) : (
                <div
                  className={cn(
                    "mt-2 truncate text-lg font-semibold tabular-nums",
                    toneTextClass(check.tone),
                  )}
                  title={check.value}
                >
                  {check.value}
                </div>
              )}
              <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                {check.detail}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ExecutiveKpis({
  model,
  loading,
}: {
  model: ExpenseDashboardModel;
  loading: boolean;
}) {
  const cards = [
    {
      label: "Чистая прибыль",
      value: formatMoneyRu(model.netProfit),
      sub:
        model.marginPercent == null
          ? "маржа не рассчитана"
          : `маржа ${formatPercent(model.marginPercent)}`,
      tone:
        model.netProfit != null && model.netProfit < 0
          ? ("danger" as Tone)
          : ("success" as Tone),
      icon: CircleDollarSign,
    },
    {
      label: "Все расходы",
      value: formatMoneyRu(model.totalExpenses),
      sub:
        model.expenseLoadPercent == null
          ? "нагрузка не рассчитана"
          : `${formatPercent(model.expenseLoadPercent)} от выручки`,
      tone:
        model.expenseLoadPercent != null && model.expenseLoadPercent > 70
          ? ("warning" as Tone)
          : ("neutral" as Tone),
      icon: WalletCards,
    },
    {
      label: "Расходы Вайлдберриз",
      value: formatMoneyRu(model.totalWbExpenses),
      sub:
        model.wbLoadPercent == null
          ? "без доли"
          : `${formatPercent(model.wbLoadPercent)} от выручки`,
      tone: "info" as Tone,
      icon: Banknote,
    },
    {
      label: "Себестоимость и прочее",
      value: formatMoneyRu(model.totalSellerExpenses),
      sub:
        model.sellerLoadPercent == null
          ? "без доли"
          : `${formatPercent(model.sellerLoadPercent)} от выручки`,
      tone: "neutral" as Tone,
      icon: Package,
    },
    {
      label: "Реклама",
      value: formatMoneyRu(model.totalAdExpenses),
      sub:
        model.adLoadPercent == null
          ? "ДРР не рассчитан"
          : `ДРР ${formatPercent(model.adLoadPercent)}`,
      tone:
        model.adLoadPercent != null && model.adLoadPercent > 18
          ? ("warning" as Tone)
          : ("neutral" as Tone),
      icon: Megaphone,
    },
    {
      label: "Логистика",
      value: formatMoneyRu(model.logisticsTotal),
      sub:
        model.logisticsSharePercent == null
          ? "доля не рассчитана"
          : `${formatPercent(model.logisticsSharePercent)} от расходов Вайлдберриз`,
      tone:
        model.logisticsSharePercent != null && model.logisticsSharePercent >= 70
          ? ("danger" as Tone)
          : ("warning" as Tone),
      icon: Truck,
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
      {cards.map((card) => (
        <MetricTile key={card.label} {...card} loading={loading} />
      ))}
    </div>
  );
}

function MetricTile({
  label,
  value,
  sub,
  tone,
  icon: Icon,
  loading,
}: {
  label: string;
  value: string;
  sub: string;
  tone: Tone;
  icon: LucideIcon;
  loading: boolean;
}) {
  return (
    <Card className={cn("overflow-hidden", toneBorderClass(tone))}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">{label}</div>
            {loading ? (
              <Skeleton className="mt-3 h-7 w-28" />
            ) : (
              <div className="mt-2 truncate text-xl font-semibold tabular-nums">
                {value}
              </div>
            )}
          </div>
          <div className={cn("rounded-md border p-2", toneIconClass(tone))}>
            <Icon className="h-4 w-4" />
          </div>
        </div>
        <div className="mt-3 text-xs text-muted-foreground">{sub}</div>
      </CardContent>
    </Card>
  );
}

function ProfitLedger({
  model,
  cascade,
  loading,
}: {
  model: ExpenseDashboardModel;
  cascade: ProfitCascadeResponse | null | undefined;
  loading: boolean;
}) {
  const totals = cascade?.cascade?.totals;
  const additionalIncome = firstNumber(totals?.additional_income);
  const rows = [
    {
      label: "Выручка",
      amount: model.revenue,
      tone: "success" as Tone,
      sign: "income",
    },
    {
      label: "Расходы продавца",
      amount: negate(model.totalSellerExpenses),
      tone: "neutral" as Tone,
      sign: "expense",
    },
    {
      label: "Расходы Вайлдберриз",
      amount: negate(model.totalWbExpenses),
      tone: "warning" as Tone,
      sign: "expense",
    },
    {
      label: "Реклама",
      amount: negate(model.totalAdExpenses),
      tone: "info" as Tone,
      sign: "expense",
    },
    {
      label: "Доплаты и компенсации",
      amount: additionalIncome,
      tone: "success" as Tone,
      sign: "income",
    },
    {
      label: "Чистая прибыль",
      amount: model.netProfit,
      tone:
        model.netProfit != null && model.netProfit < 0
          ? ("danger" as Tone)
          : ("success" as Tone),
      sign: "result",
    },
  ].filter(
    (row) => row.amount != null || row.label !== "Доплаты и компенсации",
  );

  const max = Math.max(...rows.map((row) => Math.abs(row.amount ?? 0)), 1);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Calculator className="h-4 w-4 text-muted-foreground" />
            Расчет прибыли
          </CardTitle>
          <FinalityBadge final={model.financialFinal} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, idx) => (
              <Skeleton key={idx} className="h-10 w-full" />
            ))}
          </div>
        ) : (
          rows.map((row) => {
            const value = row.amount ?? 0;
            const width = Math.max(4, (Math.abs(value) / max) * 100);
            return (
              <div
                key={row.label}
                className={cn(
                  "grid gap-2 sm:grid-cols-[180px_minmax(160px,1fr)_130px] sm:items-center",
                  row.sign === "result" && "border-t pt-3",
                )}
              >
                <div className="text-sm font-medium">{row.label}</div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn(
                      "h-full rounded-full",
                      row.tone === "success" && "bg-emerald-500",
                      row.tone === "warning" && "bg-amber-500",
                      row.tone === "danger" && "bg-red-500",
                      row.tone === "info" && "bg-sky-500",
                      row.tone === "neutral" && "bg-zinc-500",
                    )}
                    style={{ width: `${width}%` }}
                  />
                </div>
                <div
                  className={cn(
                    "text-right text-sm font-semibold tabular-nums",
                    row.sign === "expense" && "text-muted-foreground",
                    value < 0 && "text-red-700",
                  )}
                >
                  {formatMoneyRu(value)}
                </div>
              </div>
            );
          })
        )}
        {!loading && model.largestCategory && (
          <div className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
            Крупнейшая статья:{" "}
            <span className="font-medium text-foreground">
              {categoryLabel(
                model.largestCategory.category,
                model.largestCategory.category_label,
              )}
            </span>{" "}
            на сумму{" "}
            <span className="font-medium text-foreground">
              {formatMoneyRu(model.largestCategory.amount)}
            </span>
            .
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AttentionQueue({
  items,
  loading,
}: {
  items: AttentionItem[];
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldAlert className="h-4 w-4 text-muted-foreground" />
          Очередь бухгалтера
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading
          ? Array.from({ length: 4 }).map((_, idx) => (
              <Skeleton key={idx} className="h-16 w-full" />
            ))
          : items.map((item) => (
              <div
                key={item.title}
                className={cn(
                  "rounded-md border p-3",
                  toneSoftClass(item.tone),
                )}
              >
                <div className="flex items-start gap-3">
                  <item.icon
                    className={cn(
                      "mt-0.5 h-4 w-4 shrink-0",
                      toneTextClass(item.tone),
                    )}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <div className="text-sm font-medium">{item.title}</div>
                      <div
                        className={cn(
                          "whitespace-nowrap text-sm font-semibold tabular-nums",
                          toneTextClass(item.tone),
                        )}
                      >
                        {item.value}
                      </div>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {item.detail}
                    </div>
                  </div>
                </div>
              </div>
            ))}
      </CardContent>
    </Card>
  );
}

function ExpenseMixSection({
  model,
  loading,
}: {
  model: ExpenseDashboardModel;
  loading: boolean;
}) {
  const segments = [
    {
      label: "Вайлдберриз",
      value: positive(model.totalWbExpenses),
      tone: "warning" as Tone,
    },
    {
      label: "Продавец",
      value: positive(model.totalSellerExpenses),
      tone: "neutral" as Tone,
    },
    {
      label: "Реклама",
      value: positive(model.totalAdExpenses),
      tone: "info" as Tone,
    },
  ].filter((segment) => segment.value > 0);
  const total = segments.reduce((sum, segment) => sum + segment.value, 0) || 1;

  const ratios = [
    {
      label: "Нагрузка расходов",
      value: model.expenseLoadPercent,
      limit: 70,
      icon: Percent,
    },
    { label: "ДРР", value: model.adLoadPercent, limit: 18, icon: Megaphone },
    {
      label: "Логистика / Вайлдберриз",
      value: model.logisticsSharePercent,
      limit: 70,
      icon: Truck,
    },
    {
      label: "Расходы продавца / выручка",
      value: model.sellerLoadPercent,
      limit: 45,
      icon: Package,
    },
  ];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <BarChart3 className="h-4 w-4 text-muted-foreground" />
          Структура расходов
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {loading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <>
            <div className="overflow-hidden rounded-md border bg-muted/30">
              <div className="flex h-4 w-full">
                {segments.map((segment) => (
                  <div
                    key={segment.label}
                    className={cn(
                      segment.tone === "warning" && "bg-amber-500",
                      segment.tone === "neutral" && "bg-zinc-500",
                      segment.tone === "info" && "bg-sky-500",
                    )}
                    style={{ width: `${(segment.value / total) * 100}%` }}
                  />
                ))}
              </div>
              <div className="grid gap-0 sm:grid-cols-3">
                {segments.map((segment) => (
                  <div
                    key={segment.label}
                    className="border-t px-3 py-2 sm:border-r sm:last:border-r-0"
                  >
                    <div className="text-xs text-muted-foreground">
                      {segment.label}
                    </div>
                    <div className="mt-1 flex items-center justify-between gap-3">
                      <span className="text-sm font-semibold tabular-nums">
                        {formatMoneyRu(segment.value)}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatPercent((segment.value / total) * 100)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {ratios.map((ratio) => {
                const alert = ratio.value != null && ratio.value >= ratio.limit;
                return (
                  <div key={ratio.label} className="rounded-md border p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-xs text-muted-foreground">
                        {ratio.label}
                      </div>
                      <ratio.icon
                        className={cn(
                          "h-4 w-4",
                          alert ? "text-amber-600" : "text-muted-foreground",
                        )}
                      />
                    </div>
                    <div
                      className={cn(
                        "mt-2 text-lg font-semibold tabular-nums",
                        alert && "text-amber-700",
                      )}
                    >
                      {formatPercent(ratio.value)}
                    </div>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          alert ? "bg-amber-500" : "bg-emerald-500",
                        )}
                        style={{
                          width: `${clamp(Math.abs(ratio.value ?? 0), 0, 100)}%`,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ExpenseRegister({
  items,
  total,
  loading,
  onDrill,
}: {
  items: BreakdownItem[];
  total: number | null;
  loading: boolean;
  onDrill: (cat: string, label: string) => void;
}) {
  const [filter, setFilter] = useState<"all" | "wb" | "seller" | "risk">("all");
  const [statusFilter, setStatusFilter] = useState<
    "all" | "final" | "provisional" | "minus" | "unallocated"
  >("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [amountFrom, setAmountFrom] = useState("");
  const [amountTo, setAmountTo] = useState("");
  const [query, setQuery] = useState("");

  const sourceOptions = useMemo(
    () =>
      Array.from(
        new Set(
          items
            .map((item) => item.source)
            .filter((source): source is string => Boolean(source)),
        ),
      ).sort((a, b) => sourceLabel(a).localeCompare(sourceLabel(b))),
    [items],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const minAmount = parseMoneyInput(amountFrom);
    const maxAmount = parseMoneyInput(amountTo);
    return [...items]
      .filter((item) => {
        if (filter === "wb") return isWbCategory(item.category);
        if (filter === "seller") return isSellerCategory(item.category);
        if (filter === "risk") return isRiskCategory(item);
        return true;
      })
      .filter((item) => {
        if (statusFilter === "final") return item.is_final === true;
        if (statusFilter === "provisional") return item.is_final === false;
        if (statusFilter === "minus") return (item.amount ?? 0) < 0;
        if (statusFilter === "unallocated") {
          return (
            item.category === "unclassified_wb_expenses" ||
            item.source === "account_level"
          );
        }
        return true;
      })
      .filter((item) =>
        sourceFilter === "all" ? true : item.source === sourceFilter,
      )
      .filter((item) => {
        const absAmount = Math.abs(item.amount ?? 0);
        if (minAmount != null && absAmount < minAmount) return false;
        if (maxAmount != null && absAmount > maxAmount) return false;
        return true;
      })
      .filter((item) => {
        if (!needle) return true;
        return `${item.category} ${item.category_label ?? ""} ${categoryLabel(item.category, item.category_label)} ${item.source ?? ""}`
          .toLowerCase()
          .includes(needle);
      })
      .sort((a, b) => Math.abs(b.amount ?? 0) - Math.abs(a.amount ?? 0));
  }, [amountFrom, amountTo, filter, items, query, sourceFilter, statusFilter]);

  return (
    <Card className="overflow-hidden border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <CardHeader className="border-b border-zinc-200 bg-zinc-50 pb-3 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <CardTitle className="flex items-center gap-2 text-base text-zinc-950 dark:text-zinc-50">
            <ReceiptText className="h-4 w-4 text-cyan-700 dark:text-cyan-300" />
            Реестр расходов
          </CardTitle>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-end">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Поиск по статье"
                className="h-8 w-full border-zinc-200 bg-white pl-8 text-xs sm:w-52 dark:border-zinc-800 dark:bg-zinc-950"
              />
            </div>
            <Select value={sourceFilter} onValueChange={setSourceFilter}>
              <SelectTrigger className="h-8 w-full border-zinc-200 bg-white text-xs sm:w-48 dark:border-zinc-800 dark:bg-zinc-950">
                <SelectValue placeholder="Источник" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все источники</SelectItem>
                {sourceOptions.map((source) => (
                  <SelectItem key={source} value={source}>
                    {sourceLabel(source)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={statusFilter}
              onValueChange={(value) =>
                setStatusFilter(value as typeof statusFilter)
              }
            >
              <SelectTrigger className="h-8 w-full border-zinc-200 bg-white text-xs sm:w-44 dark:border-zinc-800 dark:bg-zinc-950">
                <SelectValue placeholder="Контроль" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все статусы</SelectItem>
                <SelectItem value="final">Финально</SelectItem>
                <SelectItem value="provisional">Предварительно</SelectItem>
                <SelectItem value="minus">Минусовые строки</SelectItem>
                <SelectItem value="unallocated">Без распределения</SelectItem>
              </SelectContent>
            </Select>
            <Input
              value={amountFrom}
              onChange={(event) => setAmountFrom(event.target.value)}
              placeholder="от ₽"
              className="h-8 w-full border-zinc-200 bg-white text-xs sm:w-20 dark:border-zinc-800 dark:bg-zinc-950"
              inputMode="decimal"
            />
            <Input
              value={amountTo}
              onChange={(event) => setAmountTo(event.target.value)}
              placeholder="до ₽"
              className="h-8 w-full border-zinc-200 bg-white text-xs sm:w-20 dark:border-zinc-800 dark:bg-zinc-950"
              inputMode="decimal"
            />
            <div className="flex rounded-md border border-zinc-200 bg-white p-0.5 dark:border-zinc-800 dark:bg-zinc-950">
              {[
                ["all", "Все"],
                ["wb", "Вайлдберриз"],
                ["seller", "Продавец"],
                ["risk", "Риски"],
              ].map(([key, label]) => (
                <Button
                  key={key}
                  type="button"
                  size="sm"
                  variant={filter === key ? "secondary" : "ghost"}
                  className="h-7 px-2 text-xs"
                  onClick={() => setFilter(key as typeof filter)}
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
          <Table>
            <TableHeader>
              <TableRow className="bg-zinc-100/70 hover:bg-zinc-100/70 dark:bg-zinc-900 dark:hover:bg-zinc-900">
                <TableHead>Статья</TableHead>
                <TableHead className="text-right">Сумма</TableHead>
                <TableHead className="text-right">Доля</TableHead>
                <TableHead>Контроль</TableHead>
                <TableHead className="text-right">Строк</TableHead>
                <TableHead className="w-[70px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading &&
                Array.from({ length: 8 }).map((_, idx) => (
                  <TableRow key={idx}>
                    <TableCell colSpan={6}>
                      <Skeleton className="h-7 w-full" />
                    </TableCell>
                  </TableRow>
                ))}

              {!loading && filtered.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="h-24 text-center text-muted-foreground"
                  >
                    Нет строк
                  </TableCell>
                </TableRow>
              )}

              {!loading &&
                filtered.map((item, idx) => {
                  const amount = item.amount ?? 0;
                  const share =
                    item.share_percent ??
                    (total ? (amount / total) * 100 : null);
                  const label = categoryLabel(
                    item.category,
                    item.category_label,
                  );
                  const risk = isRiskCategory(item);
                  const logistics =
                    item.category === "wb_logistics" ||
                    item.category === "wb_logistics_rebill";
                  const accent = expenseAccent(idx);
                  return (
                    <TableRow
                      key={item.category}
                      className={cn(
                        "hover:bg-zinc-50 dark:hover:bg-zinc-900/70",
                        logistics && "bg-amber-50/60 dark:bg-amber-950/10",
                        amount < 0 && "bg-red-500/5",
                      )}
                    >
                      <TableCell className="min-w-[260px]">
                        <div className="flex items-start gap-2">
                          <CategoryIcon category={item.category} risk={risk} />
                          <div className="min-w-0">
                            <div className="font-medium">{label}</div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {sourceShortLabel(item.source)}
                            </div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right font-semibold tabular-nums",
                          amount < 0 && "text-red-700",
                        )}
                      >
                        {formatMoneyRu(amount)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        <div>{formatPercent(share)}</div>
                        <div className="ml-auto mt-1 h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                          <div
                            className={cn(
                              "h-full rounded-full",
                              risk ? "bg-amber-500" : accent.bar,
                            )}
                            style={{
                              width: `${clamp(Math.abs(share ?? 0), 0, 100)}%`,
                            }}
                          />
                        </div>
                      </TableCell>
                      <TableCell>
                        {item.is_final === false ? (
                          <Badge className="border-amber-500/30 bg-amber-500/15 text-amber-700">
                            предварительно
                          </Badge>
                        ) : item.is_final == null ? (
                          <span className="text-xs text-muted-foreground">
                            нет статуса
                          </span>
                        ) : (
                          <span
                            className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/10"
                            title="Финально"
                          >
                            <span className="h-2 w-2 rounded-full bg-emerald-500" />
                          </span>
                        )}
                        {amount < 0 && (
                          <Badge className="ml-2 border-red-500/30 bg-red-500/15 text-red-700">
                            минус
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatCountOrDash(item.rows_count ?? item.row_count)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => onDrill(item.category, label)}
                          aria-label={`Открыть ${label}`}
                        >
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function LogisticsControlPanel({
  data,
  loading,
  error,
  fallbackTotal,
  fallbackShare,
  onDrill,
}: {
  data: LogisticsResponse | undefined;
  loading: boolean;
  error: Error | null;
  fallbackTotal: number | null;
  fallbackShare: number | null;
  onDrill: (category: string, label: string) => void;
}) {
  const hasDetail = !!data && !error;
  const bySku = data?.by_sku ?? [];
  const unallocatedSku = bySku.find(
    (row) => row?.group_key === "sku:unallocated" || row?.sku_id == null,
  );
  const unallocatedSkuAmount = Number(unallocatedSku?.amount ?? 0);

  const logisticsParts = [
    { label: "К клиенту", value: data?.delivery_to_client },
    { label: "Возврат", value: data?.return_from_client },
    { label: "Отмена к клиенту", value: data?.cancellation_to_client },
    { label: "Отмена обратно", value: data?.cancellation_from_client },
    { label: "Инициатива продавца", value: data?.seller_initiated_return },
    { label: "Брак", value: data?.defect_return },
  ];

  return (
    <Card className="overflow-hidden border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <CardHeader className="border-b border-zinc-200 bg-amber-50 pb-3 dark:border-zinc-800 dark:bg-amber-950/20">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base text-zinc-950 dark:text-zinc-50">
            <Truck className="h-4 w-4 text-amber-600" />
            Логистика Вайлдберриз
          </CardTitle>
          <Button
            size="sm"
            variant="outline"
            className="border-amber-200 bg-white hover:bg-amber-50 dark:border-amber-800 dark:bg-zinc-950 dark:hover:bg-amber-950/30"
            onClick={() => onDrill("wb_logistics", "Логистика Вайлдберриз")}
          >
            <FileText className="mr-2 h-4 w-4" />
            Строки
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <ApiErrorState error={error} endpoint="/money/expenses/logistics" />
        )}

        <div className="grid gap-3 sm:grid-cols-3">
          <InlineMetric
            label="Всего"
            value={formatMoneyRu(data?.total_logistics ?? fallbackTotal)}
            loading={loading && !hasDetail}
          />
          <InlineMetric
            label="Вайлдберриз"
            value={formatMoneyRu(data?.total_wb_logistics)}
            loading={loading && !hasDetail}
          />
          <InlineMetric
            label="Доля"
            value={formatPercent(
              data?.logistics_share_percent ?? fallbackShare,
            )}
            loading={loading && !hasDetail}
            tone={
              (data?.logistics_share_percent ?? fallbackShare ?? 0) >= 70
                ? "danger"
                : "neutral"
            }
          />
        </div>

        {unallocatedSkuAmount > 0 && (
          <Alert className="border-amber-500/40 bg-amber-500/10 text-amber-950 dark:text-amber-100">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Есть логистика без карточки</AlertTitle>
            <AlertDescription>
              {formatMoneyRu(unallocatedSkuAmount)} не распределено по
              карточкам.
            </AlertDescription>
          </Alert>
        )}

        {!hasDetail && !error ? (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-3/4" />
          </div>
        ) : (
          <>
            <div className="grid gap-2 sm:grid-cols-2">
              {logisticsParts.map((part, idx) => {
                const accent = expenseAccent(idx + 2);
                return (
                  <div
                    key={part.label}
                    className="rounded-md border border-zinc-200 bg-zinc-50/60 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="flex min-w-0 items-center gap-2">
                        <span
                          className={cn("h-2 w-2 rounded-full", accent.dot)}
                        />
                        <span className="truncate text-xs text-zinc-500">
                          {part.label}
                        </span>
                      </span>
                      <span className="text-sm font-semibold tabular-nums text-zinc-950 dark:text-zinc-50">
                        {formatMoneyRu(part.value)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            {Array.isArray(data?.by_logistics_type) &&
              data.by_logistics_type.length > 0 && (
                <BarBlock
                  title="Тип логистики"
                  items={data.by_logistics_type.slice(0, 6).map((row) => ({
                    label: row.label ?? row.logistics_type ?? "-",
                    amount: Number(row.amount ?? 0),
                  }))}
                  tone="warning"
                />
              )}

            {Array.isArray(data?.by_nm) && data.by_nm.length > 0 && (
              <div className="overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-800">
                <div className="border-b border-zinc-200 bg-zinc-50 px-3 py-2 text-sm font-medium dark:border-zinc-800 dark:bg-zinc-900">
                  Топ артикулов Вайлдберриз по логистике
                </div>
                <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {data.by_nm.slice(0, 6).map((row) => (
                    <div
                      key={`${row.nm_id}-${row.vendor_code}`}
                      className="grid grid-cols-[minmax(0,1fr)_120px] items-center gap-3 px-3 py-2 text-xs hover:bg-zinc-50 dark:hover:bg-zinc-900"
                    >
                      <div className="min-w-0">
                        <div className="truncate font-medium">
                          {row.vendor_code || `nm ${row.nm_id ?? "-"}`}
                        </div>
                        <div className="text-muted-foreground">
                          {row.nm_id ?? "-"}
                        </div>
                      </div>
                      <div className="text-right font-semibold tabular-nums">
                        {formatMoneyRu(row.amount)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ReportRowsDrawer({
  open,
  category,
  onClose,
  accountId,
  dateFrom,
  dateTo,
}: {
  open: boolean;
  category: DrillTarget | null;
  onClose: () => void;
  accountId: number | null | undefined;
  dateFrom: string;
  dateTo: string;
}) {
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [amountExact, setAmountExact] = useState("");
  const [amountMin, setAmountMin] = useState("");
  const [amountMax, setAmountMax] = useState("");
  const [sourceField, setSourceField] = useState("");
  const [sellerOperName, setSellerOperName] = useState("");
  const [allocatedFilter, setAllocatedFilter] = useState<
    "all" | "allocated" | "unallocated"
  >("all");
  const [quickFilter, setQuickFilter] = useState<"all" | "minus">("all");
  const limit = 100;

  useEffect(() => {
    setOffset(0);
    setSearch("");
    setAmountExact("");
    setAmountMin("");
    setAmountMax("");
    setSourceField("");
    setSellerOperName("");
    setAllocatedFilter("all");
    setQuickFilter("all");
  }, [category?.key, accountId, dateFrom, dateTo]);

  const q = useQuery({
    ...expensesReportRowsQueryOptions({
      accountId,
      dateFrom,
      dateTo,
      category: category?.category,
      skuId: category?.skuId,
      nmId: category?.nmId,
      amountExact: parseMoneyInput(amountExact),
      amountMin: parseMoneyInput(amountMin),
      amountMax: parseMoneyInput(amountMax),
      search: search.trim() || null,
      sourceField: sourceField.trim() || null,
      sellerOperName: sellerOperName.trim() || null,
      allocated:
        allocatedFilter === "all" ? null : allocatedFilter === "allocated",
      enabled: open && !!category,
      limit,
      offset,
    }),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  const rows = useMemo<ExpenseReportRow[]>(() => {
    const data = q.data as ExpenseReportRowsResult | undefined;
    if (!data) return [];
    return Array.isArray(data) ? data : (data.items ?? []);
  }, [q.data]);

  const totalCount = useMemo(() => {
    const data = q.data as ExpenseReportRowsResult | undefined;
    if (data && !Array.isArray(data) && typeof data.total === "number")
      return data.total;
    return null;
  }, [q.data]);

  const filtered = useMemo(() => {
    if (quickFilter === "minus") {
      return rows.filter((row) => (Number(row.amount) || 0) < 0);
    }
    return rows;
  }, [quickFilter, rows]);

  const pageTotal = useMemo(
    () => filtered.reduce((sum, row) => sum + (Number(row.amount) || 0), 0),
    [filtered],
  );
  const unallocatedCount = useMemo(
    () =>
      filtered.filter(
        (row) => row.sku_id == null || row.is_allocated_to_sku === false,
      ).length,
    [filtered],
  );
  const topOperation = useMemo(() => {
    const totals = new Map<string, number>();
    for (const row of filtered) {
      const key = row.seller_oper_name ?? "-";
      totals.set(key, (totals.get(key) ?? 0) + (Number(row.amount) || 0));
    }
    return (
      Array.from(totals.entries()).sort(
        (a, b) => Math.abs(b[1]) - Math.abs(a[1]),
      )[0] ?? null
    );
  }, [filtered]);

  return (
    <Sheet open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <SheetContent
        side="right"
        className="flex w-full flex-col overflow-hidden p-0 sm:max-w-6xl"
      >
        <div className="border-b bg-muted/30">
          <SheetHeader className="px-6 py-5">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2 text-[11px] font-medium uppercase text-muted-foreground">
                  <Layers className="h-3.5 w-3.5" />
                  Аудит строк отчета
                </div>
                <SheetTitle className="truncate text-xl">
                  {category?.label ?? "-"}
                </SheetTitle>
                <SheetDescription>
                  {dateFrom} - {dateTo}
                </SheetDescription>
              </div>
              <Button
                size="icon"
                variant="ghost"
                onClick={onClose}
                aria-label="Закрыть"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            {!q.isLoading && rows.length > 0 && (
              <div className="grid gap-2 pt-3 sm:grid-cols-4">
                <DrawerMetric
                  label="Сумма страницы"
                  value={formatMoneyRu(pageTotal)}
                  tone={pageTotal < 0 ? "danger" : "neutral"}
                />
                <DrawerMetric
                  label="Строк"
                  value={
                    totalCount == null
                      ? formatNumber(rows.length)
                      : `${formatNumber(rows.length)} / ${formatNumber(totalCount)}`
                  }
                />
                <DrawerMetric
                  label="Без карточки"
                  value={formatNumber(unallocatedCount)}
                  tone={unallocatedCount > 0 ? "warning" : "neutral"}
                />
                <DrawerMetric
                  label="Топ операция"
                  value={topOperation?.[0] ?? "-"}
                />
              </div>
            )}

            <div className="grid gap-2 pt-2 lg:grid-cols-[minmax(180px,1.3fr)_110px_110px_110px_minmax(150px,0.9fr)_minmax(150px,0.9fr)_220px]">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(event) => {
                    setOffset(0);
                    setSearch(event.target.value);
                  }}
                  placeholder="Артикул, штрихкод, заказ, строка Вайлдберриз"
                  className="h-9 bg-background pl-9 text-xs"
                />
              </div>
              <Input
                value={amountExact}
                onChange={(event) => {
                  setOffset(0);
                  setAmountExact(event.target.value);
                }}
                placeholder="ровно ₽"
                className="h-9 bg-background text-xs"
                inputMode="decimal"
              />
              <Input
                value={amountMin}
                onChange={(event) => {
                  setOffset(0);
                  setAmountMin(event.target.value);
                }}
                placeholder="от ₽"
                className="h-9 bg-background text-xs"
                inputMode="decimal"
              />
              <Input
                value={amountMax}
                onChange={(event) => {
                  setOffset(0);
                  setAmountMax(event.target.value);
                }}
                placeholder="до ₽"
                className="h-9 bg-background text-xs"
                inputMode="decimal"
              />
              <Input
                value={sourceField}
                onChange={(event) => {
                  setOffset(0);
                  setSourceField(event.target.value);
                }}
                placeholder="поле отчета"
                className="h-9 bg-background text-xs"
              />
              <Input
                value={sellerOperName}
                onChange={(event) => {
                  setOffset(0);
                  setSellerOperName(event.target.value);
                }}
                placeholder="операция"
                className="h-9 bg-background text-xs"
              />
              <div className="flex rounded-md border bg-background p-0.5">
                {[
                  ["all", "Все"],
                  ["allocated", "На карточке"],
                  ["unallocated", "Без карточки"],
                ].map(([key, label]) => (
                  <Button
                    key={key}
                    type="button"
                    size="sm"
                    variant={allocatedFilter === key ? "secondary" : "ghost"}
                    className="h-7 flex-1 px-2 text-[11px]"
                    onClick={() => {
                      setOffset(0);
                      setAllocatedFilter(key as typeof allocatedFilter);
                    }}
                  >
                    {label}
                  </Button>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-2 pt-2">
              {[
                {
                  label: "Ровно 1 ₽",
                  onClick: () => {
                    setOffset(0);
                    setQuickFilter("all");
                    setAmountExact("1");
                    setAmountMin("");
                    setAmountMax("");
                  },
                },
                {
                  label: "Минусовые",
                  onClick: () => {
                    setOffset(0);
                    setQuickFilter("minus");
                    setAmountExact("");
                    setAmountMin("");
                    setAmountMax("");
                  },
                },
                {
                  label: "Крупнее 10 000 ₽",
                  onClick: () => {
                    setOffset(0);
                    setQuickFilter("all");
                    setAmountExact("");
                    setAmountMin("10000");
                    setAmountMax("");
                  },
                },
                {
                  label: "Сбросить фильтр",
                  onClick: () => {
                    setOffset(0);
                    setSearch("");
                    setAmountExact("");
                    setAmountMin("");
                    setAmountMax("");
                    setSourceField("");
                    setSellerOperName("");
                    setAllocatedFilter("all");
                    setQuickFilter("all");
                  },
                },
              ].map((action) => (
                <Button
                  key={action.label}
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-8 bg-background text-xs"
                  onClick={action.onClick}
                >
                  {action.label}
                </Button>
              ))}
            </div>
          </SheetHeader>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {q.error ? (
            <ApiErrorState
              error={q.error as Error}
              endpoint="/money/expenses/report-rows"
              onRetry={() => q.refetch()}
            />
          ) : q.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              {Array.from({ length: 9 }).map((_, idx) => (
                <Skeleton key={idx} className="h-14 w-full" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <EmptyAuditState
              title="Нет строк отчета"
              detail="По этой статье за выбранный период данных нет."
              icon={FileText}
            />
          ) : filtered.length === 0 ? (
            <EmptyAuditState
              title="Ничего не найдено"
              detail="Измените поисковый запрос."
              icon={Search}
            />
          ) : (
            <div className="overflow-hidden rounded-md border bg-card">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader className="bg-muted/40">
                    <TableRow className="hover:bg-muted/40">
                      <TableHead>
                        <span className="inline-flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          Дата
                        </span>
                      </TableHead>
                      <TableHead className="text-right">Сумма</TableHead>
                      <TableHead>Операция</TableHead>
                      <TableHead>
                        <span className="inline-flex items-center gap-1">
                          <Truck className="h-3 w-3" />
                          Обоснование
                        </span>
                      </TableHead>
                      <TableHead>
                        <span className="inline-flex items-center gap-1">
                          <Package className="h-3 w-3" />
                          Карточка
                        </span>
                      </TableHead>
                      <TableHead>
                        <span className="inline-flex items-center gap-1">
                          <Hash className="h-3 w-3" />
                          След
                        </span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filtered.map((row, idx) => {
                      const amount = Number(row.amount) || 0;
                      const unallocated =
                        row.sku_id == null || row.is_allocated_to_sku === false;
                      return (
                        <TableRow
                          key={`${row.rrd_id ?? idx}-${row.source_field ?? ""}`}
                          className={cn(amount < 0 && "bg-red-500/5")}
                        >
                          <TableCell className="whitespace-nowrap align-top font-mono text-xs text-muted-foreground">
                            {row.date ?? "-"}
                          </TableCell>
                          <TableCell
                            className={cn(
                              "whitespace-nowrap text-right align-top font-semibold tabular-nums",
                              amount < 0 && "text-red-700",
                            )}
                          >
                            {formatMoneyRu(amount)}
                          </TableCell>
                          <TableCell className="max-w-[220px] align-top text-xs">
                            <div
                              className="truncate"
                              title={row.seller_oper_name ?? undefined}
                            >
                              {row.seller_oper_name ?? "-"}
                            </div>
                            {row.source_field && (
                              <div className="mt-1 font-mono text-[10px] text-muted-foreground">
                                {fieldLabel(row.source_field)}
                              </div>
                            )}
                          </TableCell>
                          <TableCell className="align-top text-xs">
                            {(row.bonus_type_name ?? row.logistics_type) ? (
                              <Badge
                                variant="secondary"
                                className="max-w-[180px] truncate text-[10px] font-normal"
                              >
                                {row.bonus_type_name ?? row.logistics_type}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground">-</span>
                            )}
                          </TableCell>
                          <TableCell className="align-top text-xs">
                            {row.nm_id || row.vendor_code || row.barcode ? (
                              <div className="space-y-0.5">
                                {row.nm_id && (
                                  <div className="font-mono tabular-nums">
                                    {row.nm_id}
                                  </div>
                                )}
                                {row.vendor_code && (
                                  <div
                                    className="max-w-[160px] truncate text-muted-foreground"
                                    title={row.vendor_code}
                                  >
                                    {row.vendor_code}
                                  </div>
                                )}
                                {row.barcode && (
                                  <div className="font-mono text-[10px] text-muted-foreground">
                                    {row.barcode}
                                  </div>
                                )}
                              </div>
                            ) : (
                              <Badge
                                variant="outline"
                                className="border-amber-300 bg-amber-50 text-[10px] text-amber-700"
                              >
                                без карточки
                              </Badge>
                            )}
                            {unallocated &&
                              (row.nm_id || row.vendor_code || row.barcode) && (
                                <Badge
                                  variant="outline"
                                  className="mt-1 border-amber-300 bg-amber-50 text-[10px] text-amber-700"
                                >
                                  без карточки
                                </Badge>
                              )}
                          </TableCell>
                          <TableCell className="align-top font-mono text-[10px] text-muted-foreground">
                            <div className="max-w-[180px] space-y-0.5">
                              {row.srid && (
                                <div className="truncate" title={row.srid}>
                                  продажа {row.srid}
                                </div>
                              )}
                              {row.order_id && (
                                <div
                                  className="truncate"
                                  title={String(row.order_id)}
                                >
                                  заказ {row.order_id}
                                </div>
                              )}
                              {row.report_id && (
                                <div
                                  className="truncate"
                                  title={String(row.report_id)}
                                >
                                  отчет {row.report_id}
                                </div>
                              )}
                              {row.rrd_id && (
                                <div
                                  className="truncate"
                                  title={String(row.rrd_id)}
                                >
                                  строка Вайлдберриз {row.rrd_id}
                                </div>
                              )}
                              {!row.srid &&
                                !row.order_id &&
                                !row.report_id &&
                                !row.rrd_id && <span>-</span>}
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}
        </div>

        {!q.isLoading && rows.length > 0 && (
          <div className="flex items-center justify-between gap-3 border-t bg-muted/20 px-6 py-3">
            <div className="text-xs text-muted-foreground">
              {formatNumber(offset + 1)}-{formatNumber(offset + rows.length)}
              {totalCount != null ? ` из ${formatNumber(totalCount)}` : ""}
              {search ? ` · найдено ${formatNumber(filtered.length)}` : ""}
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={offset === 0 || q.isFetching}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Назад
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={
                  q.isFetching ||
                  (totalCount != null
                    ? offset + limit >= totalCount
                    : rows.length < limit)
                }
                onClick={() => setOffset(offset + limit)}
              >
                Дальше
              </Button>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function InlineMetric({
  label,
  value,
  loading,
  tone = "neutral",
}: {
  label: string;
  value: string;
  loading: boolean;
  tone?: Tone;
}) {
  return (
    <div className="rounded-md border px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      {loading ? (
        <Skeleton className="mt-2 h-5 w-20" />
      ) : (
        <div
          className={cn(
            "mt-1 text-sm font-semibold tabular-nums",
            toneTextClass(tone),
          )}
        >
          {value}
        </div>
      )}
    </div>
  );
}

function DrawerMetric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: Tone;
}) {
  return (
    <div className="rounded-md border bg-background px-3 py-2">
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-1 truncate text-sm font-semibold tabular-nums",
          toneTextClass(tone),
        )}
      >
        {value}
      </div>
    </div>
  );
}

function BarBlock({
  title,
  items,
  tone,
}: {
  title: string;
  items: Array<{ label: string; amount: number }>;
  tone: Tone;
}) {
  const max = Math.max(...items.map((item) => Math.abs(item.amount)), 1);
  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">{title}</div>
      <div className="space-y-2">
        {items.map((item) => (
          <div key={item.label}>
            <div className="mb-1 flex items-center justify-between gap-3 text-xs">
              <span className="truncate">{item.label}</span>
              <span className="shrink-0 font-semibold tabular-nums">
                {formatMoneyRu(item.amount)}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full",
                  tone === "warning" ? "bg-amber-500" : "bg-zinc-500",
                )}
                style={{ width: `${(Math.abs(item.amount) / max) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyAuditState({
  title,
  detail,
  icon: Icon,
}: {
  title: string;
  detail: string;
  icon: LucideIcon;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
        <Icon className="h-6 w-6 text-muted-foreground" />
      </div>
      <div className="text-sm font-medium">{title}</div>
      <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
    </div>
  );
}

function FinalityBadge({ final }: { final: boolean }) {
  return final ? (
    <Badge className="border-emerald-500/30 bg-emerald-500/15 text-emerald-700">
      <BadgeCheck className="mr-1 h-3 w-3" />
      финально
    </Badge>
  ) : (
    <Badge className="border-amber-500/30 bg-amber-500/15 text-amber-700">
      <Clock className="mr-1 h-3 w-3" />
      предварительно
    </Badge>
  );
}

function CategoryIcon({ category, risk }: { category: string; risk: boolean }) {
  const Icon =
    category === "marketing_deduction"
      ? Megaphone
      : category === "wb_logistics" || category === "wb_logistics_rebill"
        ? Truck
        : isSellerCategory(category)
          ? Package
          : risk
            ? AlertTriangle
            : ReceiptText;
  return (
    <div
      className={cn(
        "mt-0.5 rounded-md border p-1.5",
        risk
          ? "border-amber-500/30 bg-amber-500/10 text-amber-700"
          : "text-muted-foreground",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
    </div>
  );
}

function summaryToBreakdown(summary: unknown): BreakdownResponse | null {
  const summaryRecord = asRecord(summary);
  const expenseBreakdown = asOptionalRecord(summaryRecord.expense_breakdown);
  if (!expenseBreakdown) return null;
  const kpis = asRecord(summaryRecord.kpis);
  const rawItems = Array.isArray(expenseBreakdown.items)
    ? expenseBreakdown.items
    : [];
  return {
    total_expenses: firstNumber(expenseBreakdown.total_expenses),
    total_wb_expenses: firstNumber(expenseBreakdown.total_wb_expenses),
    total_seller_expenses: firstNumber(expenseBreakdown.total_seller_expenses),
    total_ad_expenses: firstNumber(expenseBreakdown.total_ad_expenses),
    logistics_total: firstNumber(expenseBreakdown.logistics_total),
    logistics_share_percent: firstNumber(
      expenseBreakdown.logistics_share_percent,
    ),
    net_profit_after_all_expenses: firstNumber(
      expenseBreakdown.net_profit_after_all_expenses,
    ),
    revenue_final: firstNumber(
      expenseBreakdown.revenue_final,
      kpis.revenue_final,
    ),
    source_of_truth: stringOrNull(expenseBreakdown.source_of_truth),
    items: rawItems.map((rawItem) => {
      const item = asRecord(rawItem);
      const category =
        stringOrNull(item.category ?? item.group_key) ?? "unknown";
      return {
        category,
        category_label: stringOrNull(item.category_label ?? item.label),
        amount: firstNumber(item.amount),
        share_percent: firstNumber(item.share_percent),
        source: stringOrNull(item.source),
        is_final: typeof item.is_final === "boolean" ? item.is_final : null,
        row_count: firstNumber(item.row_count),
        rows_count: firstNumber(item.rows_count, item.row_count),
      };
    }),
  };
}

function buildDashboardModel({
  breakdown,
  summary,
  logistics,
  cascade,
}: {
  breakdown: BreakdownResponse | null | undefined;
  summary: unknown;
  logistics: LogisticsResponse | undefined;
  cascade: ProfitCascadeResponse | null | undefined;
}): ExpenseDashboardModel {
  const summaryRecord = asRecord(summary);
  const kpis = asRecord(summaryRecord.kpis);
  const meta = asRecord(summaryRecord.meta);
  const metaTrust = asOptionalRecord(meta.data_trust);
  const dataTrust = metaTrust ?? asRecord(summaryRecord.data_trust);
  const kpiExpenseQuality = asRecord(kpis.expense_data_quality);
  const summaryReconciliation = asOptionalRecord(
    summaryRecord.finance_reconciliation,
  );
  const kpiReconciliation = asRecord(kpis.finance_reconciliation);
  const reconciliation = summaryReconciliation ?? kpiReconciliation;
  const totals = cascade?.cascade?.totals ?? {};
  const items = Array.isArray(breakdown?.items) ? breakdown.items : [];

  const revenue = firstNumber(
    breakdown?.revenue_final,
    kpis.revenue_final,
    kpis.revenue,
    totals.gross_revenue,
  );
  const totalWbExpenses = firstNumber(
    breakdown?.total_wb_expenses,
    kpis.wb_expenses_total,
    totals.total_wb_expenses,
  );
  const totalSellerExpenses = firstNumber(
    breakdown?.total_seller_expenses,
    kpis.total_seller_expenses,
    totals.total_seller_expenses,
  );
  const totalAdExpenses = firstNumber(
    breakdown?.total_ad_expenses,
    kpis.ad_spend_final,
    totals.total_ad_expenses,
  );
  const computedTotal = sumNullable(
    totalWbExpenses,
    totalSellerExpenses,
    totalAdExpenses,
  );
  const totalExpenses = firstNumber(
    breakdown?.total_expenses,
    kpis.total_expenses,
    computedTotal,
  );
  const logisticsTotal = firstNumber(
    breakdown?.logistics_total,
    logistics?.total_logistics,
    totals.logistics_total,
  );
  const logisticsSharePercent = firstNumber(
    breakdown?.logistics_share_percent,
    logistics?.logistics_share_percent,
    totals.logistics_share_percent,
  );
  const netProfit = firstNumber(
    breakdown?.net_profit_after_all_expenses,
    kpis.net_profit_after_all_expenses,
    totals.net_profit_after_all_expenses,
  );

  const financeMismatchPercent = firstNumber(
    reconciliation.difference_percent,
    reconciliation.difference_ratio_percent,
    kpis.finance_difference_percent,
  );
  const financeMismatchAmount = firstNumber(
    reconciliation.difference_amount,
    kpis.finance_difference_amount,
  );
  const unallocatedExpenses = firstNumber(
    kpis.unallocated_expenses,
    kpiExpenseQuality.unallocated_expenses,
  );
  const negativeCommission =
    items.find(
      (item) => item.category === "wb_commission" && (item.amount ?? 0) < 0,
    )?.amount ?? null;
  const finalCategoryCount = items.filter(
    (item) => item.is_final === true,
  ).length;
  const provisionalCategoryCount = items.filter(
    (item) => item.is_final === false,
  ).length;
  const totalRows = items.reduce(
    (sum, item) => sum + (Number(item.rows_count ?? item.row_count ?? 0) || 0),
    0,
  );
  const largestCategory =
    [...items].sort(
      (a, b) => Math.abs(b.amount ?? 0) - Math.abs(a.amount ?? 0),
    )[0] ?? null;

  const modelBase = {
    revenue,
    netProfit,
    marginPercent: ratio(netProfit, revenue),
    totalExpenses,
    totalWbExpenses,
    totalSellerExpenses,
    totalAdExpenses,
    logisticsTotal,
    logisticsSharePercent,
    expenseLoadPercent: ratio(totalExpenses, revenue),
    adLoadPercent: ratio(totalAdExpenses, revenue),
    sellerLoadPercent: ratio(totalSellerExpenses, revenue),
    wbLoadPercent: ratio(totalWbExpenses, revenue),
    financialFinal:
      cascade?.financial_final === true || dataTrust.financial_final === true,
    trustState:
      cascade?.trust_state ?? stringOrNull(dataTrust.trust_state) ?? null,
    confidence:
      stringOrNull(dataTrust.confidence) ??
      stringOrNull(summaryRecord.confidence) ??
      null,
    sourceOfTruth:
      cascade?.source_of_truth ?? breakdown?.source_of_truth ?? null,
    financeMismatchPercent,
    financeMismatchAmount,
    blockingIssues: firstNumber(
      dataTrust.financial_final_blockers_total,
      dataTrust.final_profit_blockers_total,
      dataTrust.blocking_open_issues_total,
    ),
    openIssues: firstNumber(
      dataTrust.all_open_issues_total,
      dataTrust.open_issues_total,
    ),
    unallocatedExpenses,
    unallocatedPercent: ratio(unallocatedExpenses, revenue),
    negativeCommissionAmount: negativeCommission,
    categoryCount: items.length,
    finalCategoryCount,
    provisionalCategoryCount,
    totalRows,
    largestCategory,
    items,
  };

  return {
    ...modelBase,
    attention: buildAttention(modelBase),
  };
}

function buildAttention(
  model: Omit<ExpenseDashboardModel, "attention">,
): AttentionItem[] {
  const items: AttentionItem[] = [];

  if (!model.financialFinal) {
    items.push({
      tone: model.blockingIssues ? "danger" : "warning",
      icon: ShieldAlert,
      title: "Период не закрыт",
      value:
        model.blockingIssues == null
          ? "контроль"
          : formatNumber(model.blockingIssues),
      detail:
        "Финальная прибыль может измениться после догрузки finance/sales/ads.",
    });
  }

  if (
    model.financeMismatchPercent != null &&
    Math.abs(model.financeMismatchPercent) >= 5
  ) {
    items.push({
      tone: "danger",
      icon: Calculator,
      title: "Сверка finance расходится",
      value: formatPercent(model.financeMismatchPercent, 2),
      detail:
        model.financeMismatchAmount == null
          ? "Нужно сравнить строки финансового отчета и базу продаж."
          : `Сумма расхождения ${formatMoneyRu(model.financeMismatchAmount)}.`,
    });
  }

  if (
    model.logisticsSharePercent != null &&
    model.logisticsSharePercent >= 70
  ) {
    items.push({
      tone: "warning",
      icon: Truck,
      title: "Логистика давит на расходы Вайлдберриз",
      value: formatPercent(model.logisticsSharePercent),
      detail:
        "Проверьте отмены, возвраты, обратную логистику и непривязанные строки.",
    });
  }

  if (
    model.negativeCommissionAmount != null &&
    model.negativeCommissionAmount < 0
  ) {
    items.push({
      tone: "danger",
      icon: ArrowDownRight,
      title: "Комиссия Вайлдберриз ушла в минус",
      value: formatMoneyRu(model.negativeCommissionAmount),
      detail:
        "Нужно проверить sign mapping по commission/vw/vwNds до финального вывода.",
    });
  }

  if ((model.unallocatedExpenses ?? 0) > 0) {
    items.push({
      tone: "warning",
      icon: Database,
      title: "Есть общие расходы магазина",
      value: formatMoneyRu(model.unallocatedExpenses),
      detail:
        model.unallocatedPercent == null
          ? "Без доли от выручки."
          : `${formatPercent(model.unallocatedPercent)} от выручки пока не распределено по карточкам.`,
    });
  }

  if (model.netProfit != null && model.netProfit < 0) {
    items.push({
      tone: "danger",
      icon: AlertTriangle,
      title: "Период убыточный",
      value: formatMoneyRu(model.netProfit),
      detail:
        "Сначала разбирайте крупнейшие статьи и рекламу, затем себестоимость.",
    });
  }

  if (items.length === 0) {
    items.push({
      tone: "success",
      icon: ShieldCheck,
      title: "Критичных сигналов нет",
      value: "норма",
      detail: "Структура расходов выглядит ровно для выбранного периода.",
    });
  }

  return items.slice(0, 5);
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asOptionalRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function parseMoneyInput(value: string): number | null {
  const normalized = value.replace(",", ".").replace(/\s+/g, "").trim();
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function expenseAccent(index: number) {
  const accents = [
    {
      bar: "bg-emerald-600",
      dot: "bg-emerald-600",
      chip: "border border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
    },
    {
      bar: "bg-cyan-600",
      dot: "bg-cyan-600",
      chip: "border border-cyan-200 bg-cyan-50 text-cyan-800 dark:border-cyan-800 dark:bg-cyan-950 dark:text-cyan-200",
    },
    {
      bar: "bg-amber-500",
      dot: "bg-amber-500",
      chip: "border border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200",
    },
    {
      bar: "bg-rose-500",
      dot: "bg-rose-500",
      chip: "border border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200",
    },
    {
      bar: "bg-indigo-500",
      dot: "bg-indigo-500",
      chip: "border border-indigo-200 bg-indigo-50 text-indigo-800 dark:border-indigo-800 dark:bg-indigo-950 dark:text-indigo-200",
    },
    {
      bar: "bg-lime-600",
      dot: "bg-lime-600",
      chip: "border border-lime-200 bg-lime-50 text-lime-800 dark:border-lime-800 dark:bg-lime-950 dark:text-lime-200",
    },
  ];
  return accents[index % accents.length];
}

function expenseHex(index: number): string {
  const colors = [
    "#059669",
    "#0891b2",
    "#f59e0b",
    "#f43f5e",
    "#6366f1",
    "#65a30d",
  ];
  return colors[index % colors.length];
}

function normalizeChartPercent(value: number | null): number {
  if (value == null || !Number.isFinite(value)) return 0;
  return clamp(Math.abs(value), 0, 100);
}

function expensePressureTone(value: number | null): Tone {
  if (value == null) return "neutral";
  if (value >= 90) return "danger";
  if (value >= 70) return "warning";
  return "success";
}

function toneHex(tone: Tone): string {
  switch (tone) {
    case "success":
      return "#059669";
    case "warning":
      return "#f59e0b";
    case "danger":
      return "#ef4444";
    case "info":
      return "#0891b2";
    default:
      return "#71717a";
  }
}

function formatKopeks(shareOfRuble: number): string {
  const kopeks = Math.round(shareOfRuble * 100);
  if (kopeks <= 0) return "<1 коп.";
  if (kopeks >= 100) return "1 ₽";
  return `${kopeks} коп.`;
}

function formatRublePart(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "-";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1) return `${sign}${formatMoneyRu(abs)}`;
  return `${sign}${formatKopeks(abs)}`;
}

function cardLabel(item: BreakdownItem): string {
  if (item.sku_id == null && item.nm_id == null)
    return "Не распределено по карточкам";
  return (
    item.vendor_code ||
    item.label ||
    item.category_label ||
    (item.nm_id != null ? `Артикул Вайлдберриз ${item.nm_id}` : null) ||
    (item.sku_id != null ? `Внутренний товар ${item.sku_id}` : null) ||
    "Карточка"
  );
}

function shortDate(value: unknown): string {
  if (typeof value !== "string" || !value) return "-";
  const parts = value.split("-");
  if (parts.length === 3) return `${parts[2]}.${parts[1]}`;
  return value;
}

function fieldLabel(value: string | null | undefined): string {
  switch (value) {
    case "delivery_service":
      return "доставка покупателю";
    case "rebill_logistic_cost":
      return "перевыставленная логистика";
    case "paid_storage":
      return "хранение";
    case "paid_acceptance":
      return "приемка";
    case "penalty":
      return "штраф";
    case "deduction":
      return "удержание";
    case "acquiring_fee":
      return "эквайринг";
    case "ppvz_sales_commission":
      return "комиссия Вайлдберриз";
    case "payload.vw":
      return "комиссия из отчета";
    case "payload.vwNds":
      return "НДС комиссии";
    case "payload.ppvzReward":
      return "вознаграждение ПВЗ";
    default:
      return value || "-";
  }
}

function formatCountOrDash(value: unknown): string {
  const count = firstNumber(value);
  if (!count || count <= 0) return "—";
  return formatNumber(count);
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() !== "") {
      const n = Number(value);
      if (Number.isFinite(n)) return n;
    }
  }
  return null;
}

function sumNullable(...values: Array<number | null>): number | null {
  const numbers = values.filter(
    (value): value is number => value != null && Number.isFinite(value),
  );
  if (numbers.length === 0) return null;
  return numbers.reduce((sum, value) => sum + value, 0);
}

function ratio(value: number | null, base: number | null): number | null {
  if (value == null || base == null || base === 0) return null;
  return (value / base) * 100;
}

function negate(value: number | null): number | null {
  return value == null ? null : -Math.abs(value);
}

function positive(value: number | null): number {
  return Math.max(0, value ?? 0);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function isWbCategory(category: string): boolean {
  return (
    category.startsWith("wb_") ||
    [
      "storage",
      "payment_processing",
      "pvz_reward",
      "penalty",
      "deduction",
      "acceptance",
      "loyalty",
      "marketing_deduction",
    ].includes(category)
  );
}

function isSellerCategory(category: string): boolean {
  return category === "seller_cogs" || category === "seller_other_expense";
}

function isRiskCategory(item: BreakdownItem): boolean {
  return (
    (item.amount ?? 0) < 0 ||
    item.is_final === false ||
    item.category === "wb_logistics" ||
    item.category === "wb_logistics_rebill" ||
    item.category === "unclassified_wb_expenses"
  );
}

function sourceLabel(source: string | null | undefined): string {
  switch (source) {
    case "raw_finance":
      return "Сырой финансовый отчет";
    case "row_level":
      return "Строки финансового отчета";
    case "account_level":
      return "Общие расходы магазина";
    case "finance_report":
      return "Финансовый отчет Вайлдберриз";
    case "manual_cost":
      return "Себестоимость продавца";
    case "ads_api":
      return "Рекламный кабинет";
    case "mixed":
      return "Смешанный расчет";
    default:
      return source || "Источник не указан";
  }
}

function sourceShortLabel(source: string | null | undefined): string {
  switch (source) {
    case "raw_finance":
      return "сырой WB отчет";
    case "row_level":
      return "строки отчета";
    case "account_level":
      return "общий расход";
    case "finance_report":
      return "WB отчет";
    case "manual_cost":
      return "себестоимость";
    case "ads_api":
      return "реклама";
    case "mixed":
      return "смешанный расчет";
    default:
      return source || "нет источника";
  }
}

function trustStateLabel(value: string): string {
  switch (value) {
    case "financial_final":
      return "Финансово подтверждено";
    case "operational_provisional":
      return "Операционный предварительный";
    case "not_trusted":
      return "Не доверять без проверки";
    default:
      return value;
  }
}

function confidenceLabel(value: string): string {
  switch (value) {
    case "high":
      return "Высокая точность";
    case "medium":
      return "Средняя точность";
    case "low":
      return "Низкая точность";
    default:
      return value;
  }
}

function toneBorderClass(tone: Tone): string {
  switch (tone) {
    case "success":
      return "border-emerald-500/30";
    case "warning":
      return "border-amber-500/40";
    case "danger":
      return "border-red-500/40";
    case "info":
      return "border-sky-500/30";
    default:
      return "";
  }
}

function toneIconClass(tone: Tone): string {
  switch (tone) {
    case "success":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700";
    case "warning":
      return "border-amber-500/30 bg-amber-500/10 text-amber-700";
    case "danger":
      return "border-red-500/30 bg-red-500/10 text-red-700";
    case "info":
      return "border-sky-500/30 bg-sky-500/10 text-sky-700";
    default:
      return "bg-muted text-muted-foreground";
  }
}

function toneTextClass(tone: Tone): string {
  switch (tone) {
    case "success":
      return "text-emerald-700 dark:text-emerald-400";
    case "warning":
      return "text-amber-700 dark:text-amber-400";
    case "danger":
      return "text-red-700 dark:text-red-400";
    case "info":
      return "text-sky-700 dark:text-sky-400";
    default:
      return "";
  }
}

function toneSoftClass(tone: Tone): string {
  switch (tone) {
    case "success":
      return "border-emerald-500/30 bg-emerald-500/5";
    case "warning":
      return "border-amber-500/30 bg-amber-500/5";
    case "danger":
      return "border-red-500/30 bg-red-500/5";
    case "info":
      return "border-sky-500/30 bg-sky-500/5";
    default:
      return "";
  }
}
