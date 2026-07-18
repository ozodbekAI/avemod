/* eslint-disable @typescript-eslint/no-explicit-any */
// Professional finance workspace.
// UI route only: never call GET /finance.
// Data sources:
//   GET /money/summary
//   GET /marts/finance-reconciliation
//   GET /finance/report-rows
//   GET /finance/reports
//   GET /marts/account-expense-daily
//   GET /balance
//   GET /export/reconciliation.xlsx
import { createFileRoute, Link } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  Pie,
  PieChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertCircle,
  ArrowRight,
  Banknote,
  BookOpenCheck,
  CalendarDays,
  CheckCircle2,
  CircleDollarSign,
  ClipboardList,
  Download,
  FileSpreadsheet,
  FileText,
  Filter,
  Landmark,
  LayoutDashboard,
  ListFilter,
  PieChart as PieChartIcon,
  ReceiptText,
  RefreshCw,
  Search,
  ShieldAlert,
  Sigma,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";

import { PageShell } from "@/components/PageShell";
import { ExportButton } from "@/components/ExportButton";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { EndpointError } from "@/components/EndpointError";
import { FinancialFinalBlockerBanner } from "@/components/money-ui/FinancialFinalBlockerBanner";
import {
  TrustStatusBanner,
  trustInputsFromSummary,
} from "@/components/money-ui/TrustStatusBanner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ChartContainer, type ChartConfig } from "@/components/ui/chart";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { API_ENDPOINTS } from "@/lib/endpoints";
import {
  formatDate,
  formatDateTime,
  formatMoney,
  formatMoneyCompact,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import { api } from "@/lib/api";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";
import { cn } from "@/lib/utils";
import {
  fetchAccountExpenseDaily,
  fetchBusinessDaily,
  fetchFinanceReconciliation,
  fetchFinanceReportRows,
  fetchFinanceReports,
} from "@/lib/money-endpoints";
import { moneySummaryQueryOptions } from "@/lib/queries/money-summary";
import { normalizeTrust } from "@/lib/trust";

export const Route = createFileRoute("/_authenticated/finance")({
  component: FinancePage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

const PAGE_SIZE = 100;
const MINI_PAGE_SIZE = 200;

const revenueChartConfig = {
  operational: {
    label: "Операционная выручка",
    color: "var(--color-chart-1)",
  },
  finance: {
    label: "Подтверждено WB",
    color: "var(--color-chart-2)",
  },
  delta: { label: "Расхождение", color: "var(--color-chart-4)" },
} satisfies ChartConfig;

const expenseChartConfig = {
  wb: { label: "Расходы WB", color: "var(--color-chart-1)" },
  seller: { label: "Расходы продавца", color: "var(--color-chart-2)" },
  ads: { label: "Реклама", color: "var(--color-chart-3)" },
  profit: { label: "Чистая прибыль", color: "var(--color-chart-5)" },
  current: { label: "Баланс WB", color: "var(--color-chart-1)" },
  withdraw: { label: "Доступно к выводу", color: "var(--color-chart-2)" },
} satisfies ChartConfig;

const pieColors = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
  "oklch(0.58 0.16 300)",
  "oklch(0.64 0.12 35)",
  "oklch(0.52 0.10 250)",
];

function FinancePage() {
  const { activeId } = useAccounts();
  const { from: dateFrom, to: dateTo } = useDateRange();

  return (
    <PageShell>
      <FinancePageHeader />

      {!activeId ? (
        <Alert>
          <AlertTitle>Кабинет не выбран</AlertTitle>
          <AlertDescription>
            Выберите кабинет в верхней панели, чтобы открыть финансовый контур.
          </AlertDescription>
        </Alert>
      ) : (
        <FinanceWorkspace
          accountId={activeId}
          dateFrom={dateFrom}
          dateTo={dateTo}
        />
      )}
    </PageShell>
  );
}

function FinancePageHeader() {
  return (
    <div className="mb-4 overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
      <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0 px-5 py-4">
          <div className="flex items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-teal-600 text-white shadow-sm">
              <Landmark className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                Бухгалтерский контур WB
              </div>
              <h1 className="mt-1 truncate text-2xl font-semibold tracking-tight text-zinc-950">
                Финансовый кабинет
              </h1>
              <div className="mt-1 max-w-3xl text-sm text-zinc-600">
                Закрытие периода, сверка WB, расходы, выплаты и готовые выгрузки
                для бухгалтера.
              </div>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-3 border-t border-zinc-200 bg-zinc-50 lg:border-l lg:border-t-0">
          <HeaderSignal icon={BookOpenCheck} label="Сверка" value="WB" />
          <HeaderSignal icon={ReceiptText} label="Учет" value="Расходы" />
          <HeaderSignal icon={FileSpreadsheet} label="Экспорт" value="XLSX" />
        </div>
      </div>
    </div>
  );
}

function HeaderSignal({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-h-[86px] min-w-0 flex-col justify-center border-r border-zinc-200 px-4 last:border-r-0">
      <Icon className="mb-2 h-4 w-4 text-zinc-500" />
      <div className="truncate text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className="mt-0.5 truncate text-sm font-semibold text-zinc-950">
        {value}
      </div>
    </div>
  );
}

function FinanceWorkspace({
  accountId,
  dateFrom,
  dateTo,
}: {
  accountId: number;
  dateFrom: string;
  dateTo: string;
}) {
  const [section, setSection] = useState("overview");
  const moneyQ = useQuery({
    ...moneySummaryQueryOptions({ accountId, dateFrom, dateTo }),
    retry: false,
  });
  const reportsQ = useQuery({
    queryKey: ["finance-reports-package", accountId, dateFrom, dateTo],
    queryFn: () =>
      fetchFinanceReports({
        accountId,
        dateFrom,
        dateTo,
        limit: MINI_PAGE_SIZE,
      }) as Promise<any>,
    staleTime: 60_000,
  });
  const expenseQ = useQuery({
    queryKey: ["finance-account-expense-package", accountId, dateFrom, dateTo],
    queryFn: () =>
      fetchAccountExpenseDaily({
        accountId,
        dateFrom,
        dateTo,
        limit: MINI_PAGE_SIZE,
      }) as Promise<any>,
    staleTime: 60_000,
  });
  const reportRowsQ = useQuery({
    queryKey: ["finance-report-rows-package", accountId, dateFrom, dateTo],
    queryFn: () =>
      fetchFinanceReportRows({
        accountId,
        dateFrom,
        dateTo,
        limit: MINI_PAGE_SIZE,
      }) as Promise<any>,
    staleTime: 60_000,
  });
  const businessDailyQ = useQuery({
    queryKey: ["finance-business-daily-package", accountId, dateFrom, dateTo],
    queryFn: () =>
      fetchBusinessDaily({
        accountId,
        dateFrom,
        dateTo,
        limit: MINI_PAGE_SIZE,
      }) as Promise<any>,
    staleTime: 60_000,
  });
  const reconciliationQ = useQuery({
    queryKey: ["finance-reconciliation-package", accountId, dateFrom, dateTo],
    queryFn: () =>
      fetchFinanceReconciliation({
        accountId,
        dateFrom,
        dateTo,
        limit: MINI_PAGE_SIZE,
        onlyDiff: true,
      }) as Promise<any>,
    staleTime: 60_000,
  });
  const balanceQ = useQuery({
    queryKey: ["finance-balance-package", accountId, dateFrom, dateTo],
    queryFn: () =>
      api<any>(API_ENDPOINTS.finance.balance, {
        query: {
          account_id: accountId,
          date_from: dateFrom,
          date_to: dateTo,
          limit: 60,
        },
      }),
    staleTime: 30_000,
  });

  const summary = moneyQ.data as any;
  const reports = rowsFrom(reportsQ.data);
  const expenseRows = rowsFrom(expenseQ.data);
  const reportRows = rowsFrom(reportRowsQ.data);
  const businessRows = rowsFrom(businessDailyQ.data);
  const reconciliationRows = rowsFrom(reconciliationQ.data);
  const balances = rowsFrom(balanceQ.data);
  const view = useMemo(
    () =>
      buildFinanceView(
        summary,
        reports,
        expenseRows,
        reportRows,
        businessRows,
        reconciliationRows,
        balances,
        dateFrom,
        dateTo,
      ),
    [
      summary,
      reports,
      expenseRows,
      reportRows,
      businessRows,
      reconciliationRows,
      balances,
      dateFrom,
      dateTo,
    ],
  );
  const loading =
    moneyQ.isLoading ||
    reportsQ.isLoading ||
    expenseQ.isLoading ||
    reportRowsQ.isLoading ||
    businessDailyQ.isLoading ||
    balanceQ.isLoading;
  const refreshing =
    moneyQ.isFetching ||
    reportsQ.isFetching ||
    expenseQ.isFetching ||
    reportRowsQ.isFetching ||
    businessDailyQ.isFetching ||
    reconciliationQ.isFetching ||
    balanceQ.isFetching;

  const refreshAll = () => {
    void moneyQ.refetch();
    void reportsQ.refetch();
    void expenseQ.refetch();
    void reportRowsQ.refetch();
    void businessDailyQ.refetch();
    void reconciliationQ.refetch();
    void balanceQ.refetch();
  };

  return (
    <div className="space-y-4 pb-8">
      <AccountingReconciliationBoard
        accountId={accountId}
        dateFrom={dateFrom}
        dateTo={dateTo}
        view={view}
        loading={loading}
        refreshing={refreshing}
        onRefresh={refreshAll}
      />

      <ReportPackage
        accountId={accountId}
        dateFrom={dateFrom}
        dateTo={dateTo}
        view={view}
      />

      {summary && (
        <div className="grid gap-3 lg:grid-cols-2 [&_.rounded-lg]:rounded-lg">
          <TrustStatusBanner
            trust={trustInputsFromSummary(summary).trust}
            quality={trustInputsFromSummary(summary).quality}
            className="shadow-[0_14px_38px_rgba(15,23,42,0.04)]"
          />
          <FinancialFinalBlockerBanner
            accountId={accountId}
            dateFrom={dateFrom}
            dateTo={dateTo}
            summary={summary}
            className="rounded-lg shadow-[0_14px_38px_rgba(15,23,42,0.04)]"
          />
        </div>
      )}

      <DataDependencyNotice
        accountId={accountId}
        domains={["finance", "sales", "orders"]}
        className="rounded-lg border-amber-200/80 bg-amber-50/70 shadow-[0_14px_38px_rgba(15,23,42,0.04)]"
      />
      <SectionNavigator
        view={view}
        active={section}
        loading={loading}
        onSelect={setSection}
      />

      <Tabs value={section} onValueChange={setSection} className="space-y-3">
        <TabsList className="grid h-auto w-full grid-cols-2 gap-1 rounded-lg border border-zinc-200 bg-white p-1 shadow-[0_16px_45px_rgba(15,23,42,0.05)] sm:grid-cols-3 xl:grid-cols-6">
          <TabsTrigger
            value="overview"
            className="h-10 gap-1.5 rounded-md text-zinc-600 data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-none"
          >
            <LayoutDashboard className="h-3.5 w-3.5" />
            Обзор
          </TabsTrigger>
          <TabsTrigger
            value="reconciliation"
            className="h-10 gap-1.5 rounded-md text-zinc-600 data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-none"
          >
            <BookOpenCheck className="h-3.5 w-3.5" />
            Сверка
          </TabsTrigger>
          <TabsTrigger
            value="ledger"
            className="h-10 gap-1.5 rounded-md text-zinc-600 data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-none"
          >
            <ReceiptText className="h-3.5 w-3.5" />
            Строки WB
          </TabsTrigger>
          <TabsTrigger
            value="expenses"
            className="h-10 gap-1.5 rounded-md text-zinc-600 data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-none"
          >
            <PieChartIcon className="h-3.5 w-3.5" />
            Расходы
          </TabsTrigger>
          <TabsTrigger
            value="cash"
            className="h-10 gap-1.5 rounded-md text-zinc-600 data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-none"
          >
            <Wallet className="h-3.5 w-3.5" />
            Деньги
          </TabsTrigger>
          <TabsTrigger
            value="exceptions"
            className="h-10 gap-1.5 rounded-md text-zinc-600 data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-none"
          >
            <ShieldAlert className="h-3.5 w-3.5" />
            Контроль
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-3">
          <OverviewPanel view={view} loading={loading} reports={reports} />
        </TabsContent>
        <TabsContent value="reconciliation">
          <ReconciliationPanel
            accountId={accountId}
            dateFrom={dateFrom}
            dateTo={dateTo}
          />
        </TabsContent>
        <TabsContent value="ledger">
          <LedgerPanel
            accountId={accountId}
            dateFrom={dateFrom}
            dateTo={dateTo}
          />
        </TabsContent>
        <TabsContent value="expenses">
          <ExpensesPanel
            view={view}
            loading={expenseQ.isLoading}
            rows={expenseRows}
          />
        </TabsContent>
        <TabsContent value="cash">
          <CashPanel
            view={view}
            loading={balanceQ.isLoading || moneyQ.isLoading}
            rows={balances}
          />
        </TabsContent>
        <TabsContent value="exceptions">
          <ExceptionsPanel
            view={view}
            reportRows={reportRows}
            expenseRows={expenseRows}
            loading={reportRowsQ.isLoading || expenseQ.isLoading}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function AccountingReconciliationBoard({
  accountId,
  dateFrom,
  dateTo,
  view,
  loading,
  refreshing,
  onRefresh,
}: {
  accountId: number;
  dateFrom: string;
  dateTo: string;
  view: FinanceView;
  loading: boolean;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const canClose =
    view.wbReportCoverageAligned &&
    ["matched", "closed"].includes(view.reconciliationStatus);
  const decisionTone: Tone = canClose
    ? "success"
    : view.wbReportCoverageAligned
      ? "warning"
      : "danger";
  const decisionLabel = canClose
    ? "Можно закрывать"
    : view.wbReportCoverageAligned
      ? "Проверить строки"
      : "Не закрывать";
  const directFormula =
    view.operationalRevenue != null && view.financeRevenue != null
      ? `${moneyDash(view.operationalRevenue)} − ${moneyDash(view.financeRevenue)} = ${moneyDash(view.directDifferenceAmount)}`
      : "недостаточно данных";
  const tone = cockpitTone(decisionTone);

  return (
    <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.07)]">
      <div className="border-b border-zinc-200 bg-gradient-to-r from-white via-teal-50/55 to-white px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-start gap-3">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-teal-100 bg-teal-50 text-teal-700">
                <BookOpenCheck className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-xl font-semibold tracking-tight text-zinc-950">
                    Финансовое закрытие
                  </h2>
                  <span
                    className={`rounded-md border px-2 py-1 text-[11px] font-semibold uppercase ${tone.badge}`}
                  >
                    {decisionLabel}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <CockpitChip icon={CalendarDays}>
                    Период: {formatDate(dateFrom)} - {formatDate(dateTo)}
                  </CockpitChip>
                  <CockpitChip icon={FileSpreadsheet}>
                    WB: {view.wbReportCoverageLabel}
                  </CockpitChip>
                  <CockpitChip icon={BookOpenCheck}>
                    {view.reconciliationStatusLabel}
                  </CockpitChip>
                  {loading ? (
                    <CockpitChip icon={RefreshCw}>
                      Данные обновляются
                    </CockpitChip>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={onRefresh}
              disabled={refreshing}
            >
              <RefreshCw
                className={`mr-1.5 h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
              />
              Обновить
            </Button>
            <ExportButton
              endpoint={API_ENDPOINTS.exports.reconciliation}
              filenamePrefix="reconciliation"
              query={{
                account_id: accountId,
                date_from: dateFrom,
                date_to: dateTo,
              }}
              label="Сверка XLSX"
            />
          </div>
        </div>
      </div>

      <div className="p-4">
        <div className="grid gap-3 xl:grid-cols-[300px_minmax(0,1fr)]">
          <div className="rounded-lg border border-zinc-200 bg-zinc-50/70 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                  Решение бухгалтера
                </div>
                <div className={`mt-2 text-2xl font-semibold ${tone.text}`}>
                  {decisionLabel}
                </div>
              </div>
              <span
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border ${tone.icon}`}
              >
                {canClose ? (
                  <CheckCircle2 className="h-5 w-5" />
                ) : (
                  <ShieldAlert className="h-5 w-5" />
                )}
              </span>
            </div>

            <div className="mt-5 flex items-center justify-center">
              <CoverageRing
                value={view.coverage.selectedCoveragePercent}
                color={tone.hex}
              />
            </div>

            <div className="mt-5 grid grid-cols-2 gap-2">
              <CockpitStat
                label="Закрыто"
                value={`${view.coverage.coveredSelectedDays}/${view.coverage.selectedDays} дн.`}
                tone="success"
              />
              <CockpitStat
                label="Открыто"
                value={`${view.coverage.uncoveredSelectedDays} дн.`}
                tone={
                  view.coverage.uncoveredSelectedDays ? "danger" : "success"
                }
              />
              <CockpitStat
                label="Выручка без WB"
                value={moneyDash(view.uncoveredOperationalRevenue)}
                tone={
                  (view.uncoveredOperationalRevenue ?? 0) > 0
                    ? "danger"
                    : "success"
                }
              />
              <CockpitStat
                label="К выводу"
                value={moneyDash(view.withdrawCurrent)}
                tone={(view.withdrawCurrent ?? 0) > 0 ? "success" : "default"}
              />
            </div>
          </div>

          <div className="space-y-3">
            <div className="rounded-lg border border-zinc-200 bg-white p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold text-zinc-950">
                    Формула сверки
                  </div>
                  <div className="text-xs text-zinc-500">{directFormula}</div>
                </div>
                <div className={`text-sm font-semibold ${tone.text}`}>
                  {view.directDifferencePercent == null
                    ? "—"
                    : formatPercent(view.directDifferencePercent, 2)}
                </div>
              </div>
              <div className="grid items-stretch gap-2 lg:grid-cols-[minmax(0,1fr)_32px_minmax(0,1fr)_32px_minmax(0,1fr)]">
                <CockpitFormulaCard
                  icon={CircleDollarSign}
                  label="Операционная выручка"
                  period={view.selectedPeriodLabel}
                  value={moneyDash(view.operationalRevenue)}
                />
                <FormulaSignDark>−</FormulaSignDark>
                <CockpitFormulaCard
                  icon={Landmark}
                  label="Подтверждено WB"
                  period={view.wbReportCoverageLabel}
                  value={moneyDash(view.financeRevenue)}
                  tone={view.wbReportCoverageAligned ? "success" : "warning"}
                />
                <FormulaSignDark>=</FormulaSignDark>
                <CockpitFormulaCard
                  icon={Sigma}
                  label="Разрыв"
                  period={
                    view.wbReportCoverageAligned
                      ? "периоды совпадают"
                      : `нет WB за ${view.coverage.uncoveredSelectedDays} дн.`
                  }
                  value={moneyDash(view.directDifferenceAmount)}
                  tone={decisionTone}
                />
              </div>
            </div>

            <div className="grid gap-3 2xl:grid-cols-[minmax(0,1fr)_300px]">
              <div className="rounded-lg border border-zinc-200 bg-white p-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-zinc-950">
                      Календарь закрытия
                    </div>
                    <div className="text-xs text-zinc-500">
                      День зеленый, если он входит в закрытый отчет WB.
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <DarkLegendDot className="bg-emerald-500" label="WB" />
                    <DarkLegendDot className="bg-rose-500" label="Нет WB" />
                  </div>
                </div>
                <CockpitTimeline view={view} />
                <div className="mt-3 grid gap-2 md:grid-cols-3">
                  <CockpitStat
                    label="Покрыто"
                    value={view.coverage.coveredSelectedLabel}
                    tone="success"
                  />
                  <CockpitStat
                    label="Не покрыто"
                    value={view.coverage.uncoveredRangesLabel}
                    tone={
                      view.coverage.uncoveredSelectedDays ? "danger" : "success"
                    }
                  />
                  <CockpitStat
                    label="Лишнее в WB"
                    value={view.coverage.extraRangesLabel}
                    tone={view.coverage.extraReportDays ? "warning" : "default"}
                  />
                </div>
              </div>

              <div className="rounded-lg border border-zinc-200 bg-zinc-50/70 p-4">
                <div className="mb-3 text-sm font-semibold text-zinc-950">
                  Денежный контроль
                </div>
                <div className="space-y-2">
                  <DarkMoneyLine
                    label="Дневная выручка"
                    value={moneyDash(view.operationalRevenueByDays)}
                  />
                  <DarkMoneyLine
                    label="Закрытые дни"
                    value={moneyDash(view.coveredOperationalRevenue)}
                    tone="success"
                  />
                  <DarkMoneyLine
                    label="Открытые дни"
                    value={moneyDash(view.uncoveredOperationalRevenue)}
                    tone={
                      (view.uncoveredOperationalRevenue ?? 0) > 0
                        ? "danger"
                        : "success"
                    }
                  />
                  <DarkMoneyLine
                    label="Не привязано"
                    value={moneyDash(view.unallocatedExpenses)}
                    tone={
                      (view.unallocatedExpenses ?? 0) > 0
                        ? "warning"
                        : "success"
                    }
                  />
                  <DarkMoneyLine
                    label="Баланс WB"
                    value={moneyDash(view.balanceCurrent)}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function cockpitTone(tone: Tone) {
  if (tone === "success") {
    return {
      hex: "#10b981",
      text: "text-emerald-700",
      icon: "border-emerald-200 bg-emerald-50 text-emerald-700",
      badge: "border-emerald-200 bg-emerald-50 text-emerald-700",
    };
  }
  if (tone === "danger") {
    return {
      hex: "#f43f5e",
      text: "text-rose-700",
      icon: "border-rose-200 bg-rose-50 text-rose-700",
      badge: "border-rose-200 bg-rose-50 text-rose-700",
    };
  }
  if (tone === "warning") {
    return {
      hex: "#f59e0b",
      text: "text-amber-700",
      icon: "border-amber-200 bg-amber-50 text-amber-700",
      badge: "border-amber-200 bg-amber-50 text-amber-700",
    };
  }
  return {
    hex: "#71717a",
    text: "text-zinc-700",
    icon: "border-zinc-200 bg-zinc-50 text-zinc-600",
    badge: "border-zinc-200 bg-zinc-50 text-zinc-700",
  };
}

function CockpitChip({
  icon: Icon,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  children: ReactNode;
}) {
  return (
    <span className="inline-flex h-7 max-w-full items-center gap-1 rounded-md border border-zinc-200 bg-white px-2 text-xs text-zinc-700">
      <Icon className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
      <span className="truncate">{children}</span>
    </span>
  );
}

function CoverageRing({ value, color }: { value: number; color: string }) {
  const percent = Math.max(0, Math.min(100, value || 0));
  return (
    <div
      className="relative h-32 w-32 rounded-full p-3"
      style={{
        background: `conic-gradient(${color} ${percent}%, rgb(228,228,231) 0)`,
      }}
    >
      <div className="flex h-full w-full flex-col items-center justify-center rounded-full border border-zinc-200 bg-white">
        <div className="text-2xl font-semibold tabular-nums text-zinc-950">
          {formatPercent(percent, 0)}
        </div>
        <div className="text-[10px] uppercase tracking-wide text-zinc-500">
          покрытие
        </div>
      </div>
    </div>
  );
}

function CockpitStat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="min-w-0 rounded-md border border-zinc-200 bg-white px-3 py-2">
      <div className="truncate text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div
        className={`mt-1 truncate text-sm font-semibold tabular-nums ${darkToneClass(tone)}`}
      >
        {value}
      </div>
    </div>
  );
}

function CockpitFormulaCard({
  icon: Icon,
  label,
  period,
  value,
  tone = "default",
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  period: ReactNode;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-zinc-200 bg-zinc-50/70 p-3">
      <div className="flex items-center gap-2 text-xs font-medium text-zinc-500">
        <Icon className="h-3.5 w-3.5" />
        <span className="truncate">{label}</span>
      </div>
      <div
        className={`mt-2 truncate text-2xl font-semibold tabular-nums tracking-tight ${darkToneClass(tone)}`}
      >
        {value}
      </div>
      <div className="mt-1 truncate text-[11px] text-zinc-500">{period}</div>
    </div>
  );
}

function FormulaSignDark({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-16 items-center justify-center text-xl font-semibold text-zinc-400">
      {children}
    </div>
  );
}

function DarkLegendDot({
  className,
  label,
}: {
  className: string;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-zinc-500">
      <span className={`h-2 w-2 rounded-full ${className}`} />
      {label}
    </span>
  );
}

function CockpitTimeline({ view }: { view: FinanceView }) {
  const days = rangeDays(view.coverage.selected);
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(22px,1fr))] gap-1">
      {days.map((day) => {
        const covered = isDateInRanges(day, view.coverage.merged);
        const daily = view.operationalDailyData.find((row) => row.date === day);
        return (
          <div
            key={day}
            title={`${formatDate(day)} · ${
              covered ? "есть в WB" : "нет в WB"
            } · выручка ${moneyDash(daily?.revenue)}`}
            className={`h-10 rounded-md border text-center transition hover:-translate-y-0.5 ${
              covered
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-rose-200 bg-rose-50 text-rose-700"
            }`}
          >
            <div className="pt-1.5 text-[10px] font-semibold leading-none tabular-nums">
              {day.slice(8)}
            </div>
            <div className="mt-0.5 text-[9px] opacity-70">
              {covered ? "WB" : "—"}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DarkMoneyLine({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs">
      <span className="min-w-0 truncate text-zinc-500">{label}</span>
      <span
        className={`min-w-0 truncate text-right font-semibold tabular-nums ${darkToneClass(tone)}`}
      >
        {value}
      </span>
    </div>
  );
}

function darkToneClass(tone: Tone) {
  if (tone === "success") return "text-emerald-700";
  if (tone === "warning") return "text-amber-700";
  if (tone === "danger") return "text-rose-700";
  return "text-zinc-900";
}

function LegacyAccountingReconciliationBoard({
  accountId,
  dateFrom,
  dateTo,
  view,
  loading,
  refreshing,
  onRefresh,
}: {
  accountId: number;
  dateFrom: string;
  dateTo: string;
  view: FinanceView;
  loading: boolean;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const canClose =
    view.wbReportCoverageAligned &&
    ["matched", "closed"].includes(view.reconciliationStatus);
  const decisionTone: Tone = canClose
    ? "success"
    : view.wbReportCoverageAligned
      ? "warning"
      : "danger";
  const decisionLabel = canClose
    ? "Можно закрывать"
    : view.wbReportCoverageAligned
      ? "Проверить строки"
      : "Не закрывать";
  const directFormula =
    view.operationalRevenue != null && view.financeRevenue != null
      ? `${moneyDash(view.operationalRevenue)} − ${moneyDash(view.financeRevenue)} = ${moneyDash(view.directDifferenceAmount)}`
      : "недостаточно данных";
  const styles = decisionStyles(decisionTone);

  return (
    <section className="overflow-hidden rounded-lg border bg-card shadow-sm">
      <div className="border-b bg-background px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border bg-primary/10 text-primary">
                <BookOpenCheck className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <h2 className="text-lg font-semibold tracking-tight">
                  Бухгалтерская сверка периода
                </h2>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  <StatusChip icon={CalendarDays}>
                    {formatDate(dateFrom)} - {formatDate(dateTo)}
                  </StatusChip>
                  <StatusChip icon={FileSpreadsheet}>
                    WB: {view.wbReportCoverageLabel}
                  </StatusChip>
                  <StatusBadge status={view.reconciliationStatus} />
                </div>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Badge
              variant="outline"
              className={`h-8 rounded-md px-3 text-xs uppercase ${styles.badge}`}
            >
              {decisionLabel}
            </Badge>
            <Button
              size="sm"
              variant="outline"
              onClick={onRefresh}
              disabled={refreshing}
            >
              <RefreshCw
                className={`mr-1.5 h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
              />
              Обновить
            </Button>
            <ExportButton
              endpoint={API_ENDPOINTS.exports.reconciliation}
              filenamePrefix="reconciliation"
              query={{
                account_id: accountId,
                date_from: dateFrom,
                date_to: dateTo,
              }}
              label="Сверка XLSX"
            />
          </div>
        </div>
      </div>
      <div className="space-y-4 p-4">
        {loading ? (
          <div className="grid gap-3 xl:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-44 rounded-lg" />
            ))}
          </div>
        ) : (
          <>
            <div className="grid gap-3 xl:grid-cols-[280px_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.08fr)]">
              <DecisionSummary
                canClose={canClose}
                label={decisionLabel}
                tone={decisionTone}
                view={view}
              />
              <AccountingStage
                step="1"
                icon={CalendarDays}
                title="Операционный период"
                period={view.selectedPeriodLabel}
                value={moneyDash(view.operationalRevenue)}
                tone="default"
                rows={[
                  ["Дней в периоде", `${view.coverage.selectedDays}`],
                  [
                    "По дневным строкам",
                    moneyDash(view.operationalRevenueByDays),
                  ],
                  [
                    "Не покрыто WB",
                    `${view.coverage.uncoveredSelectedDays} дн.`,
                  ],
                ]}
              />
              <AccountingStage
                step="2"
                icon={FileSpreadsheet}
                title="Закрытые отчеты WB"
                period={view.wbReportCoverageLabel}
                value={moneyDash(view.financeRevenue)}
                tone={view.wbReportCoverageAligned ? "success" : "warning"}
                rows={[
                  [
                    "Покрыто выбранного периода",
                    `${view.coverage.coveredSelectedDays}/${view.coverage.selectedDays} дн.`,
                  ],
                  [
                    "Доля покрытия",
                    formatPercent(view.coverage.selectedCoveragePercent, 0),
                  ],
                  ["Лишние дни WB", `${view.coverage.extraReportDays} дн.`],
                ]}
              />
              <AccountingStage
                step="3"
                icon={Sigma}
                title="Итог сверки"
                period={
                  view.wbReportCoverageAligned
                    ? "периоды совпадают"
                    : `нет WB за ${view.coverage.uncoveredSelectedDays} дн.`
                }
                value={moneyDash(view.directDifferenceAmount)}
                tone={decisionTone}
                rows={[
                  ["Формула", directFormula],
                  [
                    "Разрыв от выручки",
                    view.directDifferencePercent == null
                      ? "—"
                      : formatPercent(view.directDifferencePercent, 2),
                  ],
                  [
                    "Открытая часть",
                    moneyDash(view.uncoveredOperationalRevenue),
                  ],
                ]}
              />
            </div>

            <div className="grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
              <div className="rounded-lg border bg-background p-3">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">
                      Календарь покрытия
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Каждый день показывает наличие закрытого отчета WB.
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <LegendDot className="bg-success/70" label="Закрыто" />
                    <LegendDot className="bg-destructive/70" label="Нет WB" />
                  </div>
                </div>
                <CoverageTimeline view={view} />
                <div className="mt-3 grid gap-2 md:grid-cols-3">
                  <MiniStat
                    label="Покрытый отрезок"
                    value={view.coverage.coveredSelectedLabel}
                    tone="success"
                  />
                  <MiniStat
                    label="Не покрыто"
                    value={view.coverage.uncoveredRangesLabel}
                    tone={
                      view.coverage.uncoveredSelectedDays ? "danger" : "success"
                    }
                  />
                  <MiniStat
                    label="Лишнее в WB"
                    value={view.coverage.extraRangesLabel}
                    tone={view.coverage.extraReportDays ? "warning" : "default"}
                  />
                </div>
              </div>

              <div className="rounded-lg border bg-background p-3">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
                  <ShieldAlert
                    className={`h-4 w-4 ${toneClass(decisionTone)}`}
                  />
                  Денежный контроль
                </div>
                <div className="space-y-2">
                  <AccountingLine
                    label="Операционная выручка"
                    value={moneyDash(view.operationalRevenue)}
                  />
                  <AccountingLine
                    label="Подтверждено WB"
                    value={moneyDash(view.financeRevenue)}
                  />
                  <AccountingLine
                    label="Прямой разрыв"
                    value={moneyDash(view.directDifferenceAmount)}
                    tone={decisionTone}
                  />
                  <AccountingLine
                    label="Выручка в днях без WB"
                    value={moneyDash(view.uncoveredOperationalRevenue)}
                    tone={
                      (view.uncoveredOperationalRevenue ?? 0) > 0
                        ? "danger"
                        : "success"
                    }
                  />
                  <AccountingLine
                    label="Доступно к выводу"
                    value={moneyDash(view.withdrawCurrent)}
                    tone={
                      (view.withdrawCurrent ?? 0) > 0 ? "success" : "default"
                    }
                  />
                </div>
                <Progress
                  value={view.coverage.selectedCoveragePercent}
                  className="mt-3 h-2"
                />
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function StatusChip({
  icon: Icon,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  children: ReactNode;
}) {
  return (
    <Badge
      variant="outline"
      className="h-6 max-w-full gap-1 rounded-md bg-card text-xs"
    >
      <Icon className="h-3 w-3 shrink-0" />
      <span className="truncate">{children}</span>
    </Badge>
  );
}

function decisionStyles(tone: Tone) {
  if (tone === "success") {
    return {
      badge: "border-success/40 bg-success/10 text-success",
      panel: "border-success/35 bg-success/5",
      value: "text-success",
    };
  }
  if (tone === "danger") {
    return {
      badge: "border-destructive/40 bg-destructive/10 text-destructive",
      panel: "border-destructive/35 bg-destructive/5",
      value: "text-destructive",
    };
  }
  if (tone === "warning") {
    return {
      badge: "border-warning/50 bg-warning/10 text-warning",
      panel: "border-warning/40 bg-warning/5",
      value: "text-warning",
    };
  }
  return {
    badge: "border-muted bg-muted/40 text-muted-foreground",
    panel: "border-border bg-muted/20",
    value: "text-foreground",
  };
}

function DecisionSummary({
  canClose,
  label,
  tone,
  view,
}: {
  canClose: boolean;
  label: string;
  tone: Tone;
  view: FinanceView;
}) {
  const styles = decisionStyles(tone);
  return (
    <div className={`rounded-lg border p-3 shadow-sm ${styles.panel}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Решение периода
          </div>
          <div className={`mt-2 text-2xl font-semibold ${styles.value}`}>
            {label}
          </div>
        </div>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border bg-background/80">
          {canClose ? (
            <CheckCircle2 className="h-4 w-4" />
          ) : (
            <ShieldAlert className="h-4 w-4" />
          )}
        </span>
      </div>
      <div className="mt-5">
        <div className="flex items-end justify-between gap-3">
          <span className="text-xs text-muted-foreground">Покрытие WB</span>
          <span className="text-xl font-semibold tabular-nums">
            {formatPercent(view.coverage.selectedCoveragePercent, 0)}
          </span>
        </div>
        <Progress
          value={view.coverage.selectedCoveragePercent}
          className="mt-2 h-2"
        />
        <div className="mt-2 text-[11px] text-muted-foreground">
          {view.coverage.coveredSelectedDays} из {view.coverage.selectedDays}{" "}
          дней закрыто
        </div>
      </div>
      <div className="mt-4 space-y-1.5">
        <AccountingLine
          label="Не закрыто"
          value={`${view.coverage.uncoveredSelectedDays} дн.`}
          tone={view.coverage.uncoveredSelectedDays ? "danger" : "success"}
        />
        <AccountingLine
          label="Выручка без WB"
          value={moneyDash(view.uncoveredOperationalRevenue)}
          tone={
            (view.uncoveredOperationalRevenue ?? 0) > 0 ? "danger" : "success"
          }
        />
      </div>
    </div>
  );
}

function AccountingStage({
  step,
  icon: Icon,
  title,
  period,
  value,
  rows,
  tone = "default",
}: {
  step: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  period: ReactNode;
  value: ReactNode;
  rows: Array<[string, ReactNode]>;
  tone?: Tone;
}) {
  const styles = decisionStyles(tone);
  return (
    <div
      className={`rounded-lg border bg-background p-3 shadow-sm ${styles.panel}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-card text-xs font-semibold">
            {step}
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-sm font-semibold">
              <Icon className="h-4 w-4 text-muted-foreground" />
              <span className="truncate">{title}</span>
            </div>
            <div className="mt-0.5 truncate text-xs text-muted-foreground">
              {period}
            </div>
          </div>
        </div>
      </div>
      <div
        className={`mt-4 truncate text-2xl font-semibold tabular-nums tracking-tight ${styles.value}`}
      >
        {value}
      </div>
      <div className="mt-3 space-y-1.5">
        {rows.map(([label, rowValue]) => (
          <AccountingLine key={label} label={label} value={rowValue} />
        ))}
      </div>
    </div>
  );
}

function AccountingLine({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md bg-muted/35 px-2 py-1.5 text-xs">
      <span className="min-w-0 truncate text-muted-foreground">{label}</span>
      <span
        className={`min-w-0 truncate text-right font-medium tabular-nums ${toneClass(tone)}`}
      >
        {value}
      </span>
    </div>
  );
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
      <span className={`h-2 w-2 rounded-full ${className}`} />
      {label}
    </span>
  );
}

function CoverageTimeline({ view }: { view: FinanceView }) {
  const days = rangeDays(view.coverage.selected);
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(20px,1fr))] gap-1">
      {days.map((day) => {
        const covered = isDateInRanges(day, view.coverage.merged);
        const daily = view.operationalDailyData.find((row) => row.date === day);
        return (
          <div
            key={day}
            title={`${formatDate(day)} · ${
              covered ? "есть в WB" : "нет в WB"
            } · выручка ${moneyDash(daily?.revenue)}`}
            className={`h-9 rounded-md border transition hover:-translate-y-0.5 ${
              covered
                ? "border-success/35 bg-success/15"
                : "border-destructive/35 bg-destructive/15"
            }`}
          >
            <div className="pt-1.5 text-center text-[10px] font-medium leading-none tabular-nums">
              {day.slice(8)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SectionNavigator({
  view,
  active,
  loading,
  onSelect,
}: {
  view: FinanceView;
  active: string;
  loading: boolean;
  onSelect: (value: string) => void;
}) {
  const sections = [
    {
      id: "overview",
      icon: LayoutDashboard,
      title: "Обзор",
      text: "Выручка, прибыль и расходы по выбранному периоду.",
      signal: moneyDash(view.expenseTotals.profit),
      tone:
        view.expenseTotals.profit < 0
          ? "danger"
          : view.expenseTotals.profit > 0
            ? "success"
            : "default",
    },
    {
      id: "reconciliation",
      icon: BookOpenCheck,
      title: "Сверка",
      text: "Расхождения между продажами и финансовым отчетом WB.",
      signal: view.reconciliationStatusLabel,
      tone:
        view.reconciliationStatus === "matched" ||
        view.reconciliationStatus === "closed"
          ? "success"
          : "warning",
    },
    {
      id: "ledger",
      icon: ReceiptText,
      title: "Строки WB",
      text: "Комиссии, логистика, удержания и сумма к перечислению.",
      signal: view.wbReportCoverageLabel,
      tone: view.wbReportCoverageAligned ? "success" : "warning",
    },
    {
      id: "expenses",
      icon: PieChartIcon,
      title: "Расходы",
      text: "Структура затрат WB, рекламы и расходов продавца.",
      signal: moneyDash(view.expenseTotals.total),
      tone: view.expenseTotals.total > 0 ? "warning" : "default",
    },
    {
      id: "cash",
      icon: Wallet,
      title: "Деньги",
      text: "Баланс, доступно к выводу и платежный контур.",
      signal: moneyDash(view.withdrawCurrent),
      tone: (view.withdrawCurrent ?? 0) > 0 ? "success" : "default",
    },
    {
      id: "exceptions",
      icon: ShieldAlert,
      title: "Контроль",
      text: "Непривязанные, нетиповые и требующие проверки строки.",
      signal: moneyDash(view.unallocatedExpenses),
      tone: (view.unallocatedExpenses ?? 0) > 0 ? "warning" : "success",
    },
  ] satisfies Array<{
    id: string;
    icon: React.ComponentType<{ className?: string }>;
    title: string;
    text: string;
    signal: ReactNode;
    tone: Tone;
  }>;

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-3 shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-zinc-950">
            <LayoutDashboard className="h-4 w-4 text-zinc-500" />
            Рабочие разделы
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            Быстрый переход в нужную детализацию без поиска по всей странице.
          </div>
        </div>
        <Badge
          variant="outline"
          className="rounded-md border-zinc-200 bg-zinc-50 text-[11px] text-zinc-600"
        >
          Детализация
        </Badge>
      </div>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        {sections.map((item, index) => {
          const Icon = item.icon;
          const selected = active === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              className={cn(
                "group min-h-[142px] rounded-lg border p-3 text-left transition duration-200",
                selected
                  ? "border-teal-200 bg-teal-50 text-zinc-950 shadow-[0_16px_38px_rgba(13,148,136,0.12)]"
                  : "border-zinc-200 bg-zinc-50/70 text-zinc-950 hover:-translate-y-0.5 hover:border-zinc-300 hover:bg-white hover:shadow-[0_14px_34px_rgba(15,23,42,0.08)]",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <span
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-md border text-xs font-semibold",
                    selected
                      ? "border-teal-200 bg-white text-teal-700"
                      : "border-zinc-200 bg-white text-zinc-500",
                  )}
                >
                  <Icon className="h-4 w-4" />
                </span>
                <span
                  className={cn(
                    "rounded-md px-2 py-1 text-[10px] font-semibold tabular-nums",
                    selected
                      ? "bg-white text-teal-700"
                      : "bg-white text-zinc-500",
                  )}
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
              </div>
              <div className="mt-3 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <div className="truncate text-sm font-semibold">
                    {item.title}
                  </div>
                  <ArrowRight
                    className={cn(
                      "h-4 w-4 shrink-0 transition group-hover:translate-x-0.5",
                      selected ? "text-teal-700" : "text-zinc-400",
                    )}
                  />
                </div>
                <div
                  className={cn(
                    "mt-1 line-clamp-2 min-h-8 text-xs",
                    selected ? "text-teal-900/70" : "text-zinc-500",
                  )}
                >
                  {item.text}
                </div>
                <div
                  className={cn(
                    "mt-3 truncate rounded-md px-2 py-1.5 text-xs font-semibold tabular-nums",
                    selected ? "bg-white" : "bg-white",
                    selected
                      ? darkToneClass(item.tone)
                      : toneClass(item.tone) || "text-zinc-700",
                  )}
                >
                  {loading ? "Загрузка..." : item.signal}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function ClosingPanel({
  view,
  loading,
}: {
  view: FinanceView;
  loading: boolean;
}) {
  const financeFinal = view.financialFinal;
  const deltaTone = !view.wbReportCoverageAligned
    ? "warning"
    : Math.abs(view.differencePercent ?? 0) > 2
      ? "danger"
      : Math.abs(view.differencePercent ?? 0) > 0.5
        ? "warning"
        : "success";

  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={CircleDollarSign}
          label="Операционная выручка"
          value={moneyDash(view.operationalRevenue)}
          sub="По продажам и заказам"
          loading={loading}
        />
        <MetricCard
          icon={Landmark}
          label="Подтверждено WB"
          value={moneyDash(view.financeRevenue)}
          sub="Финансовый отчет WB"
          tone={view.financeRevenue ? "success" : "default"}
          loading={loading}
        />
        <MetricCard
          icon={
            view.differenceAmount && view.differenceAmount < 0
              ? TrendingDown
              : TrendingUp
          }
          label="Разница сверки"
          value={moneyDash(view.differenceAmount)}
          sub={
            !view.wbReportCoverageAligned
              ? `WB покрывает: ${view.wbReportCoverageLabel}`
              : view.differencePercent == null
                ? "—"
                : formatPercent(view.differencePercent, 2)
          }
          tone={deltaTone}
          loading={loading}
        />
        <MetricCard
          icon={Wallet}
          label="Доступно к выводу"
          value={
            view.withdrawCurrent == null
              ? "нет снимка"
              : moneyDash(view.withdrawCurrent)
          }
          sub={`Баланс: ${moneyDash(view.balanceCurrent)}`}
          tone={
            view.withdrawCurrent && view.withdrawCurrent > 0
              ? "success"
              : "default"
          }
          loading={loading}
        />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            {financeFinal ? (
              <CheckCircle2 className="h-4 w-4 text-success" />
            ) : (
              <AlertCircle className="h-4 w-4 text-warning" />
            )}
            Закрытие периода
          </CardTitle>
          <CardDescription>{view.closedFinanceDisplay}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {loading ? (
            <Skeleton className="h-20" />
          ) : (
            <>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <MiniStat
                  label="Статус"
                  value={view.reconciliationStatusLabel}
                  tone={financeFinal ? "success" : "warning"}
                />
                <MiniStat
                  label="Открытый период"
                  value={moneyDash(view.openPeriodRevenue)}
                  tone={
                    (view.openPeriodRevenue ?? 0) > 0 ? "warning" : "success"
                  }
                />
                <MiniStat
                  label="Не привязано"
                  value={moneyDash(view.unallocatedExpenses)}
                  tone={
                    (view.unallocatedExpenses ?? 0) > 0 ? "warning" : "success"
                  }
                />
              </div>
              <Progress value={view.closingProgress} className="h-2" />
              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                <span>Точность сверки</span>
                <span>{formatPercent(view.closingProgress, 0)}</span>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ReportPackage({
  accountId,
  dateFrom,
  dateTo,
  view,
}: {
  accountId: number;
  dateFrom: string;
  dateTo: string;
  view: FinanceView;
}) {
  return (
    <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
      <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_390px]">
        <div className="min-w-0 p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold text-zinc-950">
                <FileSpreadsheet className="h-4 w-4 text-emerald-600" />
                Пакет бухгалтера
              </div>
              <div className="mt-1 text-xs text-zinc-500">
                Контрольные суммы и выгрузки для закрытия периода.
              </div>
            </div>
            <Badge
              variant="outline"
              className="h-7 rounded-md border-zinc-200 bg-zinc-50 px-2 text-[11px] text-zinc-600"
            >
              {formatDate(dateFrom)} - {formatDate(dateTo)}
            </Badge>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-5">
            <ReportMini
              icon={FileSpreadsheet}
              label="Покрытие WB"
              value={view.wbReportCoverageLabel}
              tone={view.wbReportCoverageAligned ? "success" : "warning"}
            />
            <ReportMini
              icon={CircleDollarSign}
              label="Выручка"
              value={moneyDash(view.operationalRevenue)}
            />
            <ReportMini
              icon={Sigma}
              label="Разрыв"
              value={moneyDash(view.directDifferenceAmount)}
              tone={
                (view.directDifferenceAmount ?? 0) === 0 ? "success" : "warning"
              }
            />
            <ReportMini
              icon={Banknote}
              label="Чистая прибыль"
              value={moneyDash(view.expenseTotals.profit)}
              tone={view.expenseTotals.profit < 0 ? "danger" : "success"}
            />
            <ReportMini
              icon={Wallet}
              label="К выводу"
              value={moneyDash(view.withdrawCurrent)}
              tone={(view.withdrawCurrent ?? 0) > 0 ? "success" : "default"}
            />
          </div>
        </div>

        <div className="border-t border-zinc-200 bg-teal-50/60 p-4 xl:border-l xl:border-t-0">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-zinc-950">Экспорт</div>
              <div className="text-xs text-zinc-500">XLSX для проверки</div>
            </div>
            <Download className="h-4 w-4 text-teal-700" />
          </div>
          <div className="grid gap-2 [&_button]:h-9 [&_button]:w-full [&_button]:justify-start [&_button]:border-teal-200 [&_button]:bg-white [&_button]:text-zinc-800 [&_button:hover]:bg-teal-100/70">
            <ExportButton
              endpoint={API_ENDPOINTS.exports.reconciliation}
              filenamePrefix="finance_reconciliation"
              query={{
                account_id: accountId,
                date_from: dateFrom,
                date_to: dateTo,
              }}
              label="Сверка"
            />
            <ExportButton
              endpoint={API_ENDPOINTS.exports.profitBySku}
              filenamePrefix="profit_by_sku"
              query={{
                account_id: accountId,
                date_from: dateFrom,
                date_to: dateTo,
              }}
              label="Прибыль по SKU"
            />
            <ExportButton
              endpoint={API_ENDPOINTS.exports.dataQuality}
              filenamePrefix="data_quality"
              query={{ account_id: accountId, only_open: true }}
              label="Качество данных"
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function OverviewPanel({
  view,
  loading,
  reports,
}: {
  view: FinanceView;
  loading: boolean;
  reports: any[];
}) {
  return (
    <div className="space-y-3">
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={ReceiptText}
          label="Расходы WB"
          value={moneyDash(view.expenseTotals.wb)}
          sub="Без рекламных затрат"
          loading={loading}
        />
        <MetricCard
          icon={ClipboardList}
          label="Расходы продавца"
          value={moneyDash(view.expenseTotals.seller)}
          sub="Себестоимость и прочие затраты"
          loading={loading}
        />
        <MetricCard
          icon={TrendingUp}
          label="Реклама"
          value={moneyDash(view.expenseTotals.ads)}
          sub={view.adSpendSourceLabel}
          loading={loading}
        />
        <MetricCard
          icon={Banknote}
          label="Чистая прибыль"
          value={moneyDash(view.expenseTotals.profit)}
          sub={view.profitConfidence}
          tone={
            view.expenseTotals.profit < 0
              ? "danger"
              : view.expenseTotals.profit > 0
                ? "success"
                : "default"
          }
          loading={loading}
        />
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
        <RevenueBridgeChart view={view} loading={loading} />
        <ExpenseCompositionChart view={view} loading={loading} />
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_420px]">
        <ExpenseDailyChart view={view} loading={loading} />
        <LatestReportsPanel rows={reports} />
      </div>
    </div>
  );
}

function ReconciliationPanel({
  accountId,
  dateFrom,
  dateTo,
}: {
  accountId: number;
  dateFrom: string;
  dateTo: string;
}) {
  const [offset, setOffset] = useState(0);
  const [onlyMismatch, setOnlyMismatch] = useState(true);
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    setOffset(0);
  }, [accountId, dateFrom, dateTo, onlyMismatch, status]);

  const query = useQuery({
    queryKey: [
      "finance-reconciliation-grid",
      accountId,
      dateFrom,
      dateTo,
      offset,
      onlyMismatch,
      status,
    ],
    queryFn: () =>
      fetchFinanceReconciliation({
        accountId,
        dateFrom,
        dateTo,
        limit: PAGE_SIZE,
        offset,
        onlyDiff: onlyMismatch,
        status: status === "all" ? undefined : status,
      }) as Promise<any>,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const rows = rowsFrom(query.data);
  const total = pageTotal(query.data);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = q
      ? rows.filter((row) =>
          [row.nm_id, row.sku_id, row.srid, row.vendor_code, row.barcode].some(
            (value) =>
              String(value ?? "")
                .toLowerCase()
                .includes(q),
          ),
        )
      : rows;
    return [...list].sort(
      (a, b) => Math.abs(rowDelta(b)) - Math.abs(rowDelta(a)),
    );
  }, [rows, search]);

  const stats = useMemo(() => {
    const acc = {
      mismatch: 0,
      missingFinance: 0,
      missingSale: 0,
      orderOnly: 0,
      absDelta: 0,
    };
    for (const row of rows) {
      const s = String(row.status ?? "");
      if (s === "mismatch") acc.mismatch += 1;
      if (s === "missing_finance") acc.missingFinance += 1;
      if (s === "missing_sale") acc.missingSale += 1;
      if (s === "order_without_followup") acc.orderOnly += 1;
      acc.absDelta += Math.abs(rowDelta(row));
    }
    return acc;
  }, [rows]);

  return (
    <div className="space-y-3">
      <div className="grid gap-2 md:grid-cols-4">
        <MetricCard
          icon={AlertCircle}
          label="Строк с расхождением"
          value={formatNumber(stats.mismatch)}
          tone={stats.mismatch ? "danger" : "success"}
          loading={query.isLoading}
        />
        <MetricCard
          icon={TrendingDown}
          label="Нет в WB"
          value={formatNumber(stats.missingFinance)}
          tone={stats.missingFinance ? "warning" : "success"}
          loading={query.isLoading}
        />
        <MetricCard
          icon={TrendingUp}
          label="Нет в продажах"
          value={formatNumber(stats.missingSale)}
          tone={stats.missingSale ? "warning" : "success"}
          loading={query.isLoading}
        />
        <MetricCard
          icon={Sigma}
          label="Сумма расхождений"
          value={moneyDash(stats.absDelta)}
          tone={stats.absDelta > 1 ? "warning" : "success"}
          loading={query.isLoading}
        />
      </div>

      <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
        <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base">Построчная сверка</CardTitle>
              <CardDescription>
                Продажи и заказы сверяются с финансовым отчетом WB по коду
                заказа и SKU продавца.
              </CardDescription>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
            >
              <RefreshCw
                className={`mr-1.5 h-3.5 w-3.5 ${query.isFetching ? "animate-spin" : ""}`}
              />
              Обновить
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 p-4">
          <div className="grid gap-2 lg:grid-cols-[minmax(220px,360px)_180px_180px_auto]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-9 pl-8 text-sm"
                placeholder="Артикул WB, SKU продавца, код заказа, штрих-код"
              />
            </div>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="h-9 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все статусы</SelectItem>
                <SelectItem value="mismatch">Есть расхождение</SelectItem>
                <SelectItem value="missing_finance">Нет в WB</SelectItem>
                <SelectItem value="missing_sale">Нет в продажах</SelectItem>
                <SelectItem value="order_without_followup">
                  Только заказ
                </SelectItem>
                <SelectItem value="matched">Сошлось</SelectItem>
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant={onlyMismatch ? "default" : "outline"}
              className="h-9"
              onClick={() => setOnlyMismatch((value) => !value)}
            >
              <Filter className="mr-1.5 h-3.5 w-3.5" />
              Только расхождения
            </Button>
          </div>

          <DataTableFrame>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Дата</TableHead>
                  <TableHead>Артикул WB</TableHead>
                  <TableHead>SKU продавца</TableHead>
                  <TableHead>Код заказа</TableHead>
                  <TableHead className="text-right">Операц.</TableHead>
                  <TableHead className="text-right">WB</TableHead>
                  <TableHead className="text-right">Разница</TableHead>
                  <TableHead className="text-right">К выплате опер.</TableHead>
                  <TableHead className="text-right">К выплате WB</TableHead>
                  <TableHead className="text-right">Разница выплат</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.isLoading ? (
                  <SkeletonRows columns={12} />
                ) : filtered.length ? (
                  filtered.map((row, index) => {
                    const ops = n(
                      row.sale_revenue ??
                        row.order_revenue ??
                        row.operational_revenue,
                    );
                    const finance = n(row.finance_revenue);
                    const delta = rowDelta(row);
                    const payDelta =
                      n(row.for_pay_delta) ??
                      (n(row.sale_for_pay) != null &&
                      n(row.finance_for_pay) != null
                        ? n(row.sale_for_pay)! - n(row.finance_for_pay)!
                        : null);
                    return (
                      <TableRow key={row.id ?? row.srid ?? index}>
                        <TableCell className="whitespace-nowrap text-xs">
                          {formatDate(
                            row.stat_date ??
                              row.finance_sale_date ??
                              row.sale_date,
                          )}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {dash(row.nm_id)}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {dash(row.sku_id)}
                        </TableCell>
                        <TableCell
                          className="max-w-[180px] truncate font-mono text-[11px]"
                          title={String(row.srid ?? "")}
                        >
                          {dash(row.srid)}
                        </TableCell>
                        <MoneyCell value={ops} />
                        <MoneyCell value={finance} />
                        <MoneyCell
                          value={delta}
                          tone={
                            delta < 0
                              ? "danger"
                              : delta > 0
                                ? "warning"
                                : "success"
                          }
                        />
                        <MoneyCell value={n(row.sale_for_pay)} />
                        <MoneyCell value={n(row.finance_for_pay)} />
                        <MoneyCell
                          value={payDelta}
                          tone={(payDelta ?? 0) === 0 ? "success" : "warning"}
                        />
                        <TableCell>
                          <StatusBadge status={row.status} />
                        </TableCell>
                        <TableCell>
                          {row.nm_id ? (
                            <Button
                              asChild
                              size="sm"
                              variant="ghost"
                              className="h-7 w-7 p-0"
                              title="Открыть карточку товара"
                            >
                              <Link
                                to={`/products/${row.nm_id}` as any}
                                aria-label="Открыть карточку товара"
                              >
                                <ArrowRight className="h-3.5 w-3.5" />
                              </Link>
                            </Button>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    );
                  })
                ) : (
                  <EmptyRow columns={12} label="Строки сверки не найдены" />
                )}
              </TableBody>
            </Table>
          </DataTableFrame>
          <Pager
            offset={offset}
            pageSize={PAGE_SIZE}
            total={total}
            count={rows.length}
            loading={query.isFetching}
            onOffset={setOffset}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function LedgerPanel({
  accountId,
  dateFrom,
  dateTo,
}: {
  accountId: number;
  dateFrom: string;
  dateTo: string;
}) {
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [docType, setDocType] = useState("all");
  const [sellerOperation, setSellerOperation] = useState("all");
  const [linkMode, setLinkMode] = useState("all");

  useEffect(() => {
    setOffset(0);
  }, [accountId, dateFrom, dateTo]);

  const query = useQuery({
    queryKey: [
      "finance-report-rows-ledger",
      accountId,
      dateFrom,
      dateTo,
      offset,
    ],
    queryFn: () =>
      fetchFinanceReportRows({
        accountId,
        dateFrom,
        dateTo,
        limit: PAGE_SIZE,
        offset,
      }) as Promise<any>,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const rows = rowsFrom(query.data);
  const total = pageTotal(query.data);
  const docTypes = useMemo(
    () => uniq(rows.map((row) => row.doc_type_name)),
    [rows],
  );
  const sellerOps = useMemo(
    () => uniq(rows.map((row) => row.seller_oper_name)),
    [rows],
  );
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (
        q &&
        ![
          row.nm_id,
          row.vendor_code,
          row.barcode,
          row.srid,
          row.title,
          row.brand,
        ].some((value) =>
          String(value ?? "")
            .toLowerCase()
            .includes(q),
        )
      )
        return false;
      if (docType !== "all" && row.doc_type_name !== docType) return false;
      if (sellerOperation !== "all" && row.seller_oper_name !== sellerOperation)
        return false;
      const linked = row.nm_id != null;
      if (linkMode === "linked" && !linked) return false;
      if (linkMode === "unlinked" && linked) return false;
      return true;
    });
  }, [rows, search, docType, sellerOperation, linkMode]);
  const totals = useMemo(() => ledgerTotals(filtered), [filtered]);

  return (
    <div className="space-y-3">
      <div className="grid gap-2 md:grid-cols-5">
        <MetricCard
          icon={Sigma}
          label="Сумма продаж"
          value={moneyDash(totals.retail)}
          loading={query.isLoading}
        />
        <MetricCard
          icon={Wallet}
          label="К перечислению"
          value={moneyDash(totals.forPay)}
          loading={query.isLoading}
        />
        <MetricCard
          icon={ReceiptText}
          label="Комиссия"
          value={moneyDash(totals.commission)}
          loading={query.isLoading}
        />
        <MetricCard
          icon={TrendingDown}
          label="Логистика"
          value={moneyDash(totals.logistics)}
          loading={query.isLoading}
        />
        <MetricCard
          icon={ShieldAlert}
          label="Штрафы и удержания"
          value={moneyDash(totals.adjustments)}
          tone={totals.adjustments > 0 ? "warning" : "default"}
          loading={query.isLoading}
        />
      </div>

      <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
        <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base">
                Строки финансового отчета WB
              </CardTitle>
              <CardDescription>
                Продажи, комиссии, логистика и суммы к перечислению из отчета
                реализации WB.
              </CardDescription>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
            >
              <RefreshCw
                className={`mr-1.5 h-3.5 w-3.5 ${query.isFetching ? "animate-spin" : ""}`}
              />
              Обновить
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 p-4">
          <div className="grid gap-2 xl:grid-cols-[minmax(220px,1fr)_180px_220px_180px]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-9 pl-8 text-sm"
                placeholder="Артикул WB, артикул продавца, код заказа, штрих-код"
              />
            </div>
            <Select value={docType} onValueChange={setDocType}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Документ: все</SelectItem>
                {docTypes.map((value) => (
                  <SelectItem key={value} value={value}>
                    {value}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={sellerOperation} onValueChange={setSellerOperation}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Операция: все</SelectItem>
                {sellerOps.map((value) => (
                  <SelectItem key={value} value={value}>
                    {value}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={linkMode} onValueChange={setLinkMode}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Привязка: все</SelectItem>
                <SelectItem value="linked">Есть артикул WB</SelectItem>
                <SelectItem value="unlinked">Без артикула WB</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <DataTableFrame>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Дата</TableHead>
                  <TableHead>Операция</TableHead>
                  <TableHead>Бонус</TableHead>
                  <TableHead>Документ</TableHead>
                  <TableHead>Артикул WB</TableHead>
                  <TableHead>Артикул продавца</TableHead>
                  <TableHead>Склад</TableHead>
                  <TableHead className="text-right">Кол-во</TableHead>
                  <TableHead className="text-right">Сумма продаж</TableHead>
                  <TableHead className="text-right">Комиссия</TableHead>
                  <TableHead className="text-right">Логистика</TableHead>
                  <TableHead className="text-right">Хранение</TableHead>
                  <TableHead className="text-right">Штраф/удерж.</TableHead>
                  <TableHead className="text-right">К перечислению</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.isLoading ? (
                  <SkeletonRows columns={14} />
                ) : filtered.length ? (
                  filtered.map((row, index) => (
                    <TableRow key={row.id ?? row.rrd_id ?? index}>
                      <TableCell className="whitespace-nowrap text-xs">
                        {formatDate(row.rr_date ?? row.date ?? row.report_date)}
                      </TableCell>
                      <TableCell className="text-xs">
                        <Badge variant="outline">
                          {dash(row.seller_oper_name)}
                        </Badge>
                      </TableCell>
                      <TableCell
                        className="max-w-[180px] truncate text-xs"
                        title={String(row.bonus_type_name ?? "")}
                      >
                        {dash(row.bonus_type_name)}
                      </TableCell>
                      <TableCell className="text-xs">
                        {dash(row.doc_type_name)}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {row.nm_id ?? (
                          <span className="text-warning">нет артикула</span>
                        )}
                      </TableCell>
                      <TableCell
                        className="max-w-[160px] truncate text-xs"
                        title={String(row.vendor_code ?? "")}
                      >
                        {dash(row.vendor_code ?? row.sa_name)}
                      </TableCell>
                      <TableCell
                        className="max-w-[160px] truncate text-xs"
                        title={String(row.office_name ?? "")}
                      >
                        {dash(row.office_name)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {dash(row.quantity)}
                      </TableCell>
                      <MoneyCell value={n(row.retail_amount ?? row.amount)} />
                      <MoneyCell
                        value={n(
                          row.ppvz_sales_commission ??
                            row.commission_amount ??
                            row.commission,
                        )}
                      />
                      <MoneyCell value={rowLogistics(row)} />
                      <MoneyCell value={n(row.paid_storage)} />
                      <MoneyCell
                        value={(n(row.penalty) ?? 0) + (n(row.deduction) ?? 0)}
                        tone={
                          (n(row.penalty) ?? 0) + (n(row.deduction) ?? 0) > 0
                            ? "warning"
                            : "default"
                        }
                      />
                      <MoneyCell value={n(row.for_pay ?? row.ppvz_for_pay)} />
                    </TableRow>
                  ))
                ) : (
                  <EmptyRow columns={14} label="Строки отчета не найдены" />
                )}
              </TableBody>
            </Table>
          </DataTableFrame>
          <Pager
            offset={offset}
            pageSize={PAGE_SIZE}
            total={total}
            count={rows.length}
            loading={query.isFetching}
            onOffset={setOffset}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function ExpensesPanel({
  view,
  rows,
  loading,
}: {
  view: FinanceView;
  rows: any[];
  loading: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard
          icon={ReceiptText}
          label="Расходы WB"
          value={moneyDash(view.expenseTotals.wb)}
          loading={loading}
        />
        <MetricCard
          icon={ClipboardList}
          label="Расходы продавца"
          value={moneyDash(view.expenseTotals.seller)}
          loading={loading}
        />
        <MetricCard
          icon={TrendingUp}
          label="Реклама"
          value={moneyDash(view.expenseTotals.ads)}
          loading={loading}
        />
        <MetricCard
          icon={Sigma}
          label="Итого WB + реклама"
          value={moneyDash(view.expenseTotals.total)}
          tone={view.expenseTotals.total > 0 ? "warning" : "default"}
          loading={loading}
        />
        <MetricCard
          icon={Banknote}
          label="Чистая прибыль"
          value={moneyDash(view.expenseTotals.profit)}
          tone={view.expenseTotals.profit < 0 ? "danger" : "success"}
          loading={loading}
        />
        <MetricCard
          icon={ShieldAlert}
          label="Не классифицировано"
          value={moneyDash(view.expenseTotals.other)}
          tone={view.expenseTotals.other > 0 ? "warning" : "success"}
          loading={loading}
        />
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_420px]">
        <ExpenseDailyChart view={view} loading={loading} />
        <ExpenseCompositionChart view={view} loading={loading} />
      </div>

      <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
        <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
          <CardTitle className="text-base">Расходы по дням</CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          <DataTableFrame className="max-h-[560px]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Дата</TableHead>
                  <TableHead className="text-right">WB</TableHead>
                  <TableHead className="text-right">Продавец</TableHead>
                  <TableHead className="text-right">Реклама</TableHead>
                  <TableHead className="text-right">Итого</TableHead>
                  <TableHead className="text-right">Прибыль</TableHead>
                  <TableHead>Качество</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <SkeletonRows columns={7} />
                ) : rows.length ? (
                  rows.map((row, index) => (
                    <TableRow key={row.id ?? index}>
                      <TableCell className="whitespace-nowrap text-xs">
                        {formatDate(row.stat_date ?? row.date)}
                      </TableCell>
                      <MoneyCell value={n(row.total_wb_expenses)} />
                      <MoneyCell value={n(row.total_seller_expenses)} />
                      <MoneyCell value={n(row.ad_spend_final)} />
                      <MoneyCell
                        value={n(row.total_expense)}
                        tone={
                          (n(row.total_expense) ?? 0) > 0
                            ? "warning"
                            : "default"
                        }
                      />
                      <MoneyCell
                        value={n(row.net_profit_after_all_expenses)}
                        tone={
                          (n(row.net_profit_after_all_expenses) ?? 0) < 0
                            ? "danger"
                            : "success"
                        }
                      />
                      <TableCell>
                        <QualityBadge value={row.expense_data_quality} />
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <EmptyRow columns={7} label="Расходы за период не найдены" />
                )}
              </TableBody>
            </Table>
          </DataTableFrame>
        </CardContent>
      </Card>
    </div>
  );
}

function CashPanel({
  view,
  rows,
  loading,
}: {
  view: FinanceView;
  rows: any[];
  loading: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Wallet}
          label="Текущий баланс WB"
          value={moneyDash(view.balanceCurrent)}
          loading={loading}
        />
        <MetricCard
          icon={Banknote}
          label="Доступно к выводу"
          value={moneyDash(view.withdrawCurrent)}
          tone={(view.withdrawCurrent ?? 0) > 0 ? "success" : "default"}
          loading={loading}
        />
        <MetricCard
          icon={Landmark}
          label="Баланс на конец периода"
          value={moneyDash(view.balanceEnd)}
          loading={loading}
        />
        <MetricCard
          icon={Download}
          label="К выводу на конец периода"
          value={moneyDash(view.withdrawEnd)}
          tone={(view.withdrawEnd ?? 0) > 0 ? "success" : "default"}
          loading={loading}
        />
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_420px]">
        <BalanceChart view={view} loading={loading} />
        <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
          <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
            <CardTitle className="text-base">Платежный контур</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 p-4">
            <CashLine
              label="Ожидаемая выплата"
              value={moneyDash(view.expectedPayout)}
            />
            <CashLine
              label="Дата следующей выплаты"
              value={
                view.nextPayoutDate ? formatDate(view.nextPayoutDate) : "—"
              }
            />
            <CashLine
              label="Заморожено в остатках"
              value={moneyDash(view.frozenStock)}
              tone={(view.frozenStock ?? 0) > 0 ? "warning" : "default"}
            />
            <CashLine
              label="Заморожено к выплате"
              value={moneyDash(view.frozenPayout)}
              tone={(view.frozenPayout ?? 0) > 0 ? "warning" : "default"}
            />
            <CashLine
              label="Долг WB"
              value={moneyDash(view.wbDebt)}
              tone={(view.wbDebt ?? 0) > 0 ? "danger" : "default"}
            />
          </CardContent>
        </Card>
      </div>

      <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
        <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
          <CardTitle className="text-base">Снимки баланса WB</CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          <DataTableFrame className="max-h-[420px]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Дата снимка</TableHead>
                  <TableHead>Валюта</TableHead>
                  <TableHead className="text-right">Баланс</TableHead>
                  <TableHead className="text-right">К выводу</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <SkeletonRows columns={4} />
                ) : rows.length ? (
                  rows.map((row, index) => (
                    <TableRow key={row.id ?? index}>
                      <TableCell className="whitespace-nowrap text-xs">
                        {formatDateTime(row.snapshot_at)}
                      </TableCell>
                      <TableCell className="text-xs">
                        {dash(row.currency)}
                      </TableCell>
                      <MoneyCell value={n(row.current)} />
                      <MoneyCell
                        value={n(row.for_withdraw)}
                        tone={
                          (n(row.for_withdraw) ?? 0) > 0 ? "success" : "default"
                        }
                      />
                    </TableRow>
                  ))
                ) : (
                  <EmptyRow columns={4} label="Снимки баланса не найдены" />
                )}
              </TableBody>
            </Table>
          </DataTableFrame>
        </CardContent>
      </Card>
    </div>
  );
}

function ExceptionsPanel({
  view,
  reportRows,
  expenseRows,
  loading,
}: {
  view: FinanceView;
  reportRows: any[];
  expenseRows: any[];
  loading: boolean;
}) {
  const unlinkedRows = reportRows.filter((row) => row.nm_id == null);
  const accountLevelDays = expenseRows.filter(
    (row) =>
      (n(row.source_rows) ?? 0) > 0 || (n(row.other_wb_expenses) ?? 0) > 0,
  );
  const unlinkedTotal = unlinkedRows.reduce(
    (sum, row) => sum + Math.abs(n(row.retail_amount ?? row.for_pay) ?? 0),
    0,
  );

  return (
    <div className="space-y-3">
      <div className="grid gap-2 md:grid-cols-3">
        <MetricCard
          icon={ShieldAlert}
          label="Без артикула WB"
          value={moneyDash(unlinkedTotal)}
          tone={unlinkedTotal > 0 ? "warning" : "success"}
          loading={loading}
        />
        <MetricCard
          icon={ListFilter}
          label="Строк без карточки"
          value={formatNumber(unlinkedRows.length)}
          tone={unlinkedRows.length ? "warning" : "success"}
          loading={loading}
        />
        <MetricCard
          icon={ReceiptText}
          label="Расходы уровня кабинета"
          value={moneyDash(view.unallocatedExpenses)}
          tone={(view.unallocatedExpenses ?? 0) > 0 ? "warning" : "success"}
          loading={loading}
        />
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
          <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
            <CardTitle className="text-base">Строки WB без артикула</CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <DataTableFrame className="max-h-[420px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Дата</TableHead>
                    <TableHead>Операция</TableHead>
                    <TableHead>Документ</TableHead>
                    <TableHead>Бонус</TableHead>
                    <TableHead className="text-right">Сумма</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    <SkeletonRows columns={5} />
                  ) : unlinkedRows.length ? (
                    unlinkedRows.map((row, index) => (
                      <TableRow
                        key={row.id ?? row.rrd_id ?? index}
                        className="bg-warning/5"
                      >
                        <TableCell className="whitespace-nowrap text-xs">
                          {formatDate(row.rr_date)}
                        </TableCell>
                        <TableCell className="text-xs">
                          <Badge variant="outline">
                            {dash(row.seller_oper_name)}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs">
                          {dash(row.doc_type_name)}
                        </TableCell>
                        <TableCell
                          className="max-w-[180px] truncate text-xs"
                          title={String(row.bonus_type_name ?? "")}
                        >
                          {dash(row.bonus_type_name)}
                        </TableCell>
                        <MoneyCell
                          value={n(row.retail_amount ?? row.for_pay)}
                          tone="warning"
                        />
                      </TableRow>
                    ))
                  ) : (
                    <EmptyRow
                      columns={5}
                      label="Все строки привязаны к артикулу WB"
                    />
                  )}
                </TableBody>
              </Table>
            </DataTableFrame>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
          <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
            <CardTitle className="text-base">
              Расходы уровня кабинета по дням
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <DataTableFrame className="max-h-[420px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Дата</TableHead>
                    <TableHead className="text-right">
                      Строк источника
                    </TableHead>
                    <TableHead className="text-right">Расходы WB</TableHead>
                    <TableHead className="text-right">Прочие WB</TableHead>
                    <TableHead>Качество</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    <SkeletonRows columns={5} />
                  ) : accountLevelDays.length ? (
                    accountLevelDays.map((row, index) => (
                      <TableRow key={row.id ?? index}>
                        <TableCell className="whitespace-nowrap text-xs">
                          {formatDate(row.stat_date)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatNumber(n(row.source_rows))}
                        </TableCell>
                        <MoneyCell value={n(row.total_wb_expenses)} />
                        <MoneyCell
                          value={n(row.other_wb_expenses)}
                          tone={
                            (n(row.other_wb_expenses) ?? 0) > 0
                              ? "warning"
                              : "default"
                          }
                        />
                        <TableCell>
                          <QualityBadge value={row.expense_data_quality} />
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <EmptyRow
                      columns={5}
                      label="Расходы уровня кабинета не найдены"
                    />
                  )}
                </TableBody>
              </Table>
            </DataTableFrame>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function RevenueBridgeChart({
  view,
  loading,
}: {
  view: FinanceView;
  loading: boolean;
}) {
  const data = [
    {
      label: "Операц.",
      operational: view.operationalRevenue ?? 0,
      finance: 0,
      delta: 0,
    },
    {
      label: "WB",
      operational: 0,
      finance: view.financeRevenue ?? 0,
      delta: 0,
    },
    {
      label: "Разница",
      operational: 0,
      finance: 0,
      delta: view.differenceAmount ?? 0,
    },
  ];

  return (
    <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
      <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
        <CardTitle className="text-base">Выручка и сверка</CardTitle>
        <CardDescription>{view.reconciliationStatusLabel}</CardDescription>
      </CardHeader>
      <CardContent className="p-4">
        {loading ? (
          <Skeleton className="h-[260px]" />
        ) : (
          <ChartContainer
            config={revenueChartConfig}
            className="h-[260px] w-full"
          >
            <BarChart
              data={data}
              margin={{ left: 8, right: 8, top: 12, bottom: 0 }}
            >
              <CartesianGrid vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} />
              <YAxis
                tickFormatter={(value) => formatMoneyCompact(Number(value))}
                tickLine={false}
                axisLine={false}
                width={70}
              />
              <Tooltip formatter={(value: any) => moneyDash(Number(value))} />
              <Bar
                dataKey="operational"
                fill="var(--color-operational)"
                radius={[4, 4, 0, 0]}
              />
              <Bar
                dataKey="finance"
                fill="var(--color-finance)"
                radius={[4, 4, 0, 0]}
              />
              <Bar
                dataKey="delta"
                fill="var(--color-delta)"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}

function ExpenseDailyChart({
  view,
  loading,
}: {
  view: FinanceView;
  loading: boolean;
}) {
  return (
    <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
      <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
        <CardTitle className="text-base">Динамика расходов и прибыли</CardTitle>
      </CardHeader>
      <CardContent className="p-4">
        {loading ? (
          <Skeleton className="h-[280px]" />
        ) : view.dailyExpenseData.length ? (
          <ChartContainer
            config={expenseChartConfig}
            className="h-[280px] w-full"
          >
            <ComposedChart
              data={view.dailyExpenseData}
              margin={{ left: 8, right: 8, top: 12, bottom: 0 }}
            >
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                minTickGap={18}
              />
              <YAxis
                tickFormatter={(value) => formatMoneyCompact(Number(value))}
                tickLine={false}
                axisLine={false}
                width={70}
              />
              <Tooltip formatter={(value: any) => moneyDash(Number(value))} />
              <Bar
                dataKey="wb"
                stackId="expenses"
                fill="var(--color-wb)"
                radius={[3, 3, 0, 0]}
              />
              <Bar
                dataKey="seller"
                stackId="expenses"
                fill="var(--color-seller)"
                radius={[3, 3, 0, 0]}
              />
              <Bar
                dataKey="ads"
                stackId="expenses"
                fill="var(--color-ads)"
                radius={[3, 3, 0, 0]}
              />
              <Line
                dataKey="profit"
                type="monotone"
                stroke="var(--color-profit)"
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ChartContainer>
        ) : (
          <EmptyChart label="Дневные расходы не найдены" />
        )}
      </CardContent>
    </Card>
  );
}

function ExpenseCompositionChart({
  view,
  loading,
}: {
  view: FinanceView;
  loading: boolean;
}) {
  return (
    <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
      <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
        <CardTitle className="text-base">Структура расходов</CardTitle>
      </CardHeader>
      <CardContent className="p-4">
        {loading ? (
          <Skeleton className="h-[280px]" />
        ) : view.expenseComposition.length ? (
          <div className="grid gap-3 md:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-1 2xl:grid-cols-[220px_minmax(0,1fr)]">
            <ChartContainer
              config={{
                amount: { label: "Сумма", color: "var(--color-chart-1)" },
              }}
              className="h-[220px] w-full"
            >
              <PieChart>
                <Tooltip formatter={(value: any) => moneyDash(Number(value))} />
                <Pie
                  data={view.expenseComposition}
                  dataKey="amount"
                  nameKey="label"
                  innerRadius={58}
                  outerRadius={86}
                  paddingAngle={2}
                >
                  {view.expenseComposition.map((entry, index) => (
                    <Cell
                      key={entry.label}
                      fill={pieColors[index % pieColors.length]}
                    />
                  ))}
                </Pie>
              </PieChart>
            </ChartContainer>
            <div className="space-y-2">
              {view.expenseComposition.slice(0, 8).map((item, index) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between gap-3 text-sm"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-sm"
                      style={{
                        background: pieColors[index % pieColors.length],
                      }}
                    />
                    <span className="truncate text-muted-foreground">
                      {item.label}
                    </span>
                  </div>
                  <span className="font-medium tabular-nums">
                    {moneyDash(item.amount)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <EmptyChart label="Структура расходов не найдена" />
        )}
      </CardContent>
    </Card>
  );
}

function BalanceChart({
  view,
  loading,
}: {
  view: FinanceView;
  loading: boolean;
}) {
  return (
    <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
      <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
        <CardTitle className="text-base">Баланс и доступно к выводу</CardTitle>
      </CardHeader>
      <CardContent className="p-4">
        {loading ? (
          <Skeleton className="h-[280px]" />
        ) : view.balanceData.length ? (
          <ChartContainer
            config={expenseChartConfig}
            className="h-[280px] w-full"
          >
            <AreaChart
              data={view.balanceData}
              margin={{ left: 8, right: 8, top: 12, bottom: 0 }}
            >
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                minTickGap={18}
              />
              <YAxis
                tickFormatter={(value) => formatMoneyCompact(Number(value))}
                tickLine={false}
                axisLine={false}
                width={70}
              />
              <Tooltip formatter={(value: any) => moneyDash(Number(value))} />
              <Area
                dataKey="current"
                type="monotone"
                fill="var(--color-current)"
                fillOpacity={0.18}
                stroke="var(--color-current)"
                strokeWidth={2}
              />
              <Area
                dataKey="withdraw"
                type="monotone"
                fill="var(--color-withdraw)"
                fillOpacity={0.16}
                stroke="var(--color-withdraw)"
                strokeWidth={2}
              />
            </AreaChart>
          </ChartContainer>
        ) : (
          <EmptyChart label="Снимки баланса не найдены" />
        )}
      </CardContent>
    </Card>
  );
}

function LatestReportsPanel({ rows }: { rows: any[] }) {
  return (
    <Card className="rounded-lg border-zinc-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,0.06)]">
      <CardHeader className="border-b border-zinc-100 bg-zinc-50/70 p-4 pb-3">
        <CardTitle className="text-base">Отчеты WB</CardTitle>
      </CardHeader>
      <CardContent className="p-4">
        <DataTableFrame className="max-h-[280px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Номер отчета</TableHead>
                <TableHead>Период</TableHead>
                <TableHead>Создан</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length ? (
                rows.slice(0, 8).map((row, index) => (
                  <TableRow key={row.report_id ?? row.id ?? index}>
                    <TableCell className="font-mono text-xs">
                      {dash(row.report_id ?? row.id)}
                    </TableCell>
                    <TableCell className="text-xs">
                      {formatDate(row.date_from)} - {formatDate(row.date_to)}
                    </TableCell>
                    <TableCell className="text-xs">
                      {formatDate(row.create_date ?? row.created_at)}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <EmptyRow columns={3} label="Отчеты WB не найдены" />
              )}
            </TableBody>
          </Table>
        </DataTableFrame>
      </CardContent>
    </Card>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  sub,
  tone = "default",
  loading,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  loading?: boolean;
}) {
  return (
    <Card className="overflow-hidden rounded-lg border-zinc-200 bg-white shadow-[0_16px_45px_rgba(15,23,42,0.05)] transition hover:border-zinc-300 hover:shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
      <CardContent className="p-3.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
              {label}
            </div>
            {loading ? (
              <Skeleton className="mt-2 h-6 w-28" />
            ) : (
              <div
                className={`mt-1 truncate text-xl font-semibold tabular-nums tracking-tight ${toneClass(tone)}`}
              >
                {value}
              </div>
            )}
            {sub ? (
              <div className="mt-1 truncate text-[11px] text-zinc-500">
                {sub}
              </div>
            ) : null}
          </div>
          <span
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-md border bg-zinc-50",
              tone === "success" && "border-emerald-200 text-emerald-700",
              tone === "warning" && "border-amber-200 text-amber-700",
              tone === "danger" && "border-rose-200 text-rose-700",
              tone === "default" && "border-zinc-200 text-zinc-500",
            )}
          >
            <Icon className="h-4 w-4" />
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function MiniStat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white px-2.5 py-2 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
      <div className="truncate text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div
        className={`mt-0.5 truncate font-semibold tabular-nums ${toneClass(tone)}`}
      >
        {value}
      </div>
    </div>
  );
}

function ReportMini({
  icon: Icon,
  label,
  value,
  tone = "default",
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="flex min-h-[74px] min-w-0 items-start gap-2 rounded-lg border border-zinc-200 bg-zinc-50/70 px-3 py-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.75)]">
      <span
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-white",
          tone === "success" && "border-emerald-200 text-emerald-700",
          tone === "warning" && "border-amber-200 text-amber-700",
          tone === "danger" && "border-rose-200 text-rose-700",
          tone === "default" && "border-zinc-200 text-zinc-500",
        )}
      >
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <div className="truncate text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
          {label}
        </div>
        <div
          className={`mt-1 line-clamp-2 text-sm font-semibold leading-snug tabular-nums ${toneClass(tone)}`}
        >
          {value}
        </div>
      </div>
    </div>
  );
}

function CashLine({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm">
      <span className="min-w-0 truncate text-zinc-500">{label}</span>
      <span className={`font-medium tabular-nums ${toneClass(tone)}`}>
        {value}
      </span>
    </div>
  );
}

function StatusBadge({ status }: { status: any }) {
  const s = String(status ?? "not_available").toLowerCase();
  const map: Record<string, { cls: string; label: string }> = {
    matched: {
      cls: "border-success/40 bg-success/10 text-success",
      label: "сошлось",
    },
    closed: {
      cls: "border-success/40 bg-success/10 text-success",
      label: "закрыто",
    },
    mismatch: {
      cls: "border-destructive/40 bg-destructive/10 text-destructive",
      label: "расхождение",
    },
    critical_mismatch: {
      cls: "border-destructive/40 bg-destructive/10 text-destructive",
      label: "критично",
    },
    warning: {
      cls: "border-warning/50 bg-warning/10 text-warning",
      label: "внимание",
    },
    pending: {
      cls: "border-warning/50 bg-warning/10 text-warning",
      label: "ожидание",
    },
    open: {
      cls: "border-warning/50 bg-warning/10 text-warning",
      label: "открыто",
    },
    missing_finance: {
      cls: "border-warning/50 bg-warning/10 text-warning",
      label: "нет в WB",
    },
    missing_sale: {
      cls: "border-warning/50 bg-warning/10 text-warning",
      label: "нет в продажах",
    },
    order_without_followup: {
      cls: "border-warning/50 bg-warning/10 text-warning",
      label: "только заказ",
    },
    not_available: {
      cls: "border-muted bg-muted/40 text-muted-foreground",
      label: "нет данных",
    },
  };
  const item = map[s] ?? {
    cls: "border-muted bg-muted/30 text-muted-foreground",
    label: "неизвестно",
  };
  return (
    <Badge
      variant="outline"
      className={`whitespace-nowrap text-[10px] uppercase ${item.cls}`}
    >
      {item.label}
    </Badge>
  );
}

function QualityBadge({ value }: { value: any }) {
  const q = String(value ?? "partial");
  const tone: Tone =
    q === "complete"
      ? "success"
      : q === "unclassified_present" || q === "ad_double_count_risk"
        ? "warning"
        : "default";
  return (
    <Badge
      variant="outline"
      className={`text-[10px] uppercase ${toneClass(tone)}`}
    >
      {qualityLabel(q)}
    </Badge>
  );
}

function MoneyCell({
  value,
  tone = "default",
}: {
  value: number | null | undefined;
  tone?: Tone;
}) {
  return (
    <TableCell className={`text-right tabular-nums ${toneClass(tone)}`}>
      {moneyDash(value)}
    </TableCell>
  );
}

function DataTableFrame({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`overflow-auto rounded-lg border border-zinc-200 bg-white shadow-[0_16px_45px_rgba(15,23,42,0.05)] ${className}`}
    >
      {children}
    </div>
  );
}

function Pager({
  offset,
  pageSize,
  total,
  count,
  loading,
  onOffset,
}: {
  offset: number;
  pageSize: number;
  total: number | null;
  count: number;
  loading: boolean;
  onOffset: (value: number) => void;
}) {
  const start = count ? offset + 1 : 0;
  const end = Math.min(offset + count, total ?? offset + count);
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
      <span>
        Показано {start}-{end}
        {total != null ? ` из ${total}` : ""}
      </span>
      <div className="flex gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={offset === 0 || loading}
          onClick={() => onOffset(Math.max(0, offset - pageSize))}
        >
          Назад
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={
            loading ||
            (total != null ? offset + pageSize >= total : count < pageSize)
          }
          onClick={() => onOffset(offset + pageSize)}
        >
          Вперед
        </Button>
      </div>
    </div>
  );
}

function SkeletonRows({
  columns,
  rows = 6,
}: {
  columns: number;
  rows?: number;
}) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <TableRow key={rowIndex}>
          {Array.from({ length: columns }).map((__, colIndex) => (
            <TableCell key={colIndex}>
              <Skeleton className="h-4 w-full" />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

function EmptyRow({ columns, label }: { columns: number; label: string }) {
  return (
    <TableRow>
      <TableCell
        colSpan={columns}
        className="py-8 text-center text-sm text-muted-foreground"
      >
        {label}
      </TableCell>
    </TableRow>
  );
}

function EmptyChart({ label }: { label: string }) {
  return (
    <div className="flex h-[220px] items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-zinc-50 text-sm text-zinc-500">
      {label}
    </div>
  );
}

type Tone = "default" | "success" | "warning" | "danger";

function toneClass(tone: Tone) {
  if (tone === "success") return "text-success";
  if (tone === "warning") return "text-warning";
  if (tone === "danger") return "text-destructive";
  return "";
}

interface FinanceView {
  financialFinal: boolean;
  operationalRevenue: number | null;
  financeRevenue: number | null;
  differenceAmount: number | null;
  differencePercent: number | null;
  openPeriodRevenue: number | null;
  reconciliationStatus: string;
  reconciliationStatusLabel: string;
  closedFinanceDisplay: string;
  closingProgress: number;
  latestReportPeriod: string;
  selectedPeriodLabel: string;
  wbReportCoverageLabel: string;
  wbReportCoverageAligned: boolean;
  wbReportCoverageNote: string;
  coverage: ReportCoverage;
  operationalRevenueByDays: number | null;
  coveredOperationalRevenue: number | null;
  uncoveredOperationalRevenue: number | null;
  directDifferenceAmount: number | null;
  directDifferencePercent: number | null;
  balanceCurrent: number | null;
  withdrawCurrent: number | null;
  balanceEnd: number | null;
  withdrawEnd: number | null;
  expectedPayout: number | null;
  nextPayoutDate: string | null;
  frozenStock: number | null;
  frozenPayout: number | null;
  wbDebt: number | null;
  unallocatedExpenses: number | null;
  adSpendSourceLabel: string;
  profitConfidence: string;
  expenseTotals: {
    wb: number;
    seller: number;
    ads: number;
    total: number;
    profit: number;
    commission: number;
    logistics: number;
    storage: number;
    acceptance: number;
    paymentProcessing: number;
    penaltiesAndDeductions: number;
    other: number;
  };
  expenseComposition: Array<{ label: string; amount: number }>;
  dailyExpenseData: Array<{
    date: string;
    label: string;
    wb: number;
    seller: number;
    ads: number;
    total: number;
    profit: number;
  }>;
  operationalDailyData: Array<{
    date: string;
    label: string;
    revenue: number;
    payout: number;
    expenses: number;
    profit: number;
    coveredByWb: boolean;
  }>;
  balanceData: Array<{
    date: string;
    label: string;
    current: number;
    withdraw: number;
  }>;
}

function buildFinanceView(
  summary: any,
  reports: any[],
  expenseRows: any[],
  reportRows: any[],
  businessRows: any[],
  reconciliationRows: any[],
  balances: any[],
  dateFrom: string,
  dateTo: string,
): FinanceView {
  const fr = summary?.finance_reconciliation ?? {};
  const kpis = summary?.kpis ?? {};
  const expenses = summary?.expenses ?? {};
  const cash = summary?.cash_and_stock ?? {};
  const trust = normalizeTrust(summary ?? {});
  const operationalRevenue =
    n(fr.operational_revenue) ??
    n(kpis.finance_reconciliation_operational_revenue) ??
    n(kpis.revenue_final) ??
    n(kpis.revenue);
  const financeRevenue =
    n(fr.finance_confirmed_revenue) ?? n(kpis.finance_confirmed_revenue);
  const computedDiff =
    operationalRevenue != null && financeRevenue != null
      ? Math.abs(operationalRevenue - financeRevenue)
      : null;
  const differenceAmount =
    n(fr.difference_amount) ??
    n(kpis.finance_difference_amount) ??
    computedDiff;
  const differencePercent =
    n(fr.difference_percent) ?? n(kpis.finance_difference_percent);
  const status = String(
    fr.status ?? kpis.finance_reconciliation_status ?? "not_available",
  );
  const closedDate =
    fr.closed_finance_period_label ??
    (fr.closed_finance_date_to ? formatDate(fr.closed_finance_date_to) : null);
  const absPct = Math.abs(differencePercent ?? 0);
  const closingProgress =
    differencePercent == null
      ? 0
      : Math.max(0, Math.min(100, 100 - absPct * 12.5));

  const latestReport = reports[0];
  const latestReportPeriod = latestReport
    ? `${formatDate(latestReport.date_from ?? latestReport.period_from)} - ${formatDate(latestReport.date_to ?? latestReport.period_to)}`
    : "—";
  const reportCoverage = computeReportCoverage(reports, dateFrom, dateTo);
  const selectedPeriodLabel = `${formatDate(dateFrom)} - ${formatDate(dateTo)}`;
  const operationalDailyData = [...businessRows]
    .sort((a, b) =>
      String(a.stat_date ?? a.date ?? "").localeCompare(
        String(b.stat_date ?? b.date ?? ""),
      ),
    )
    .map((row) => {
      const rowDate = String(row.stat_date ?? row.date ?? "").slice(0, 10);
      return {
        date: rowDate,
        label: shortDate(rowDate),
        revenue: n(row.revenue ?? row.revenue_final) ?? 0,
        payout: n(row.payout ?? row.final_for_pay) ?? 0,
        expenses: n(row.expenses ?? row.total_expense) ?? 0,
        profit: n(row.profit ?? row.net_profit_after_all_expenses) ?? 0,
        coveredByWb: isDateInRanges(rowDate, reportCoverage.merged),
      };
    });
  const operationalRevenueByDays = operationalDailyData.length
    ? sumNumbers(operationalDailyData.map((row) => row.revenue))
    : null;
  const coveredOperationalRevenue = operationalDailyData.length
    ? sumNumbers(
        operationalDailyData
          .filter((row) => row.coveredByWb)
          .map((row) => row.revenue),
      )
    : null;
  const uncoveredOperationalRevenue = operationalDailyData.length
    ? sumNumbers(
        operationalDailyData
          .filter((row) => !row.coveredByWb)
          .map((row) => row.revenue),
      )
    : null;
  const directDifferenceAmount =
    operationalRevenue != null && financeRevenue != null
      ? operationalRevenue - financeRevenue
      : null;
  const directDifferencePercent =
    directDifferenceAmount != null && operationalRevenue
      ? (directDifferenceAmount / operationalRevenue) * 100
      : null;

  const expenseTotalsFromRows = expenseRows.reduce(
    (acc, row) => {
      acc.wb += n(row.total_wb_expenses) ?? 0;
      acc.seller += n(row.total_seller_expenses) ?? 0;
      acc.ads += n(row.ad_spend_final) ?? 0;
      acc.total += n(row.total_expense) ?? 0;
      acc.profit += n(row.net_profit_after_all_expenses) ?? 0;
      acc.commission += n(row.wb_commission ?? row.commission) ?? 0;
      acc.logistics +=
        (n(row.wb_logistics) ?? 0) +
        (n(row.wb_logistics_rebill) ?? 0) +
        (n(row.logistics) ?? 0);
      acc.storage += n(row.storage) ?? 0;
      acc.acceptance += n(row.acceptance ?? row.paid_acceptance) ?? 0;
      acc.paymentProcessing +=
        n(row.payment_processing ?? row.acquiring_fee) ?? 0;
      acc.penaltiesAndDeductions +=
        (n(row.penalty ?? row.penalties) ?? 0) +
        (n(row.deduction ?? row.deductions) ?? 0) +
        (n(row.loyalty) ?? 0);
      acc.other += n(row.other_wb_expenses) ?? 0;
      return acc;
    },
    {
      wb: 0,
      seller: 0,
      ads: 0,
      total: 0,
      profit: 0,
      commission: 0,
      logistics: 0,
      storage: 0,
      acceptance: 0,
      paymentProcessing: 0,
      penaltiesAndDeductions: 0,
      other: 0,
    },
  );

  const expenseTotals = {
    wb: n(kpis.wb_expenses_total) ?? expenseTotalsFromRows.wb,
    seller:
      n(kpis.total_seller_expenses ?? kpis.total_seller_costs) ??
      expenseTotalsFromRows.seller,
    ads: n(kpis.ad_spend_final ?? kpis.ad_spend) ?? expenseTotalsFromRows.ads,
    total:
      (n(kpis.wb_expenses_total) ?? expenseTotalsFromRows.wb) +
      (n(kpis.ad_spend_final ?? kpis.ad_spend) ?? expenseTotalsFromRows.ads),
    profit:
      n(kpis.net_profit_after_all_expenses) ?? expenseTotalsFromRows.profit,
    commission: n(kpis.wb_commission) ?? expenseTotalsFromRows.commission,
    logistics:
      (n(kpis.wb_logistics) ?? 0) + (n(kpis.wb_logistics_rebill) ?? 0) ||
      expenseTotalsFromRows.logistics,
    storage: n(kpis.storage) ?? expenseTotalsFromRows.storage,
    acceptance: n(kpis.acceptance) ?? expenseTotalsFromRows.acceptance,
    paymentProcessing:
      n(kpis.payment_processing) ?? expenseTotalsFromRows.paymentProcessing,
    penaltiesAndDeductions:
      (n(kpis.penalty) ?? 0) +
        (n(kpis.deduction) ?? 0) +
        (n(kpis.loyalty) ?? 0) || expenseTotalsFromRows.penaltiesAndDeductions,
    other: n(kpis.other_wb_expenses) ?? expenseTotalsFromRows.other,
  };

  const expenseComposition = [
    ["Комиссия WB", expenseTotals.commission],
    ["Эквайринг", expenseTotals.paymentProcessing],
    ["Логистика", expenseTotals.logistics],
    ["Хранение", expenseTotals.storage],
    ["Приемка", expenseTotals.acceptance],
    ["Штрафы и удержания", expenseTotals.penaltiesAndDeductions],
    ["Реклама", expenseTotals.ads],
    ["Расходы продавца", expenseTotals.seller],
    ["Прочие расходы WB", expenseTotals.other],
  ]
    .map(([label, amount]) => ({
      label: String(label),
      amount: Number(amount),
    }))
    .filter((item) => Math.abs(item.amount) > 0.01)
    .sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount));

  const dailyExpenseData = [...expenseRows]
    .sort((a, b) =>
      String(a.stat_date ?? "").localeCompare(String(b.stat_date ?? "")),
    )
    .map((row) => ({
      date: String(row.stat_date ?? row.date ?? ""),
      label: shortDate(row.stat_date ?? row.date),
      wb: n(row.total_wb_expenses) ?? 0,
      seller: n(row.total_seller_expenses) ?? 0,
      ads: n(row.ad_spend_final) ?? 0,
      total: n(row.total_expense) ?? 0,
      profit: n(row.net_profit_after_all_expenses) ?? 0,
    }));

  const balanceData = [...balances]
    .sort((a, b) =>
      String(a.snapshot_at ?? "").localeCompare(String(b.snapshot_at ?? "")),
    )
    .map((row) => ({
      date: String(row.snapshot_at ?? ""),
      label: shortDate(row.snapshot_at),
      current: n(row.current) ?? 0,
      withdraw: n(row.for_withdraw) ?? 0,
    }));

  const latestBalance = balances[0];
  const fallbackCurrent = n(latestBalance?.current);
  const fallbackWithdraw = n(latestBalance?.for_withdraw);
  const unlinkedReportTotal = reportRows
    .filter((row) => row.nm_id == null)
    .reduce(
      (sum, row) => sum + Math.abs(n(row.retail_amount ?? row.for_pay) ?? 0),
      0,
    );
  const mismatchesTotal = reconciliationRows.reduce(
    (sum, row) => sum + Math.abs(rowDelta(row)),
    0,
  );
  const finalStatus = trust.financialFinal
    ? status
    : status === "matched" && mismatchesTotal === 0
      ? "matched"
      : status;

  return {
    financialFinal: Boolean(trust.financialFinal),
    operationalRevenue,
    financeRevenue,
    differenceAmount,
    differencePercent,
    openPeriodRevenue: n(fr.open_operational_period_revenue),
    reconciliationStatus: finalStatus,
    reconciliationStatusLabel: statusLabel(finalStatus),
    closedFinanceDisplay: trust.financialFinal
      ? (closedDate ?? "Закрыто")
      : "Период не закрыт",
    closingProgress,
    latestReportPeriod,
    selectedPeriodLabel,
    wbReportCoverageLabel: reportCoverage.label,
    wbReportCoverageAligned: reportCoverage.aligned,
    wbReportCoverageNote: reportCoverage.note,
    coverage: reportCoverage,
    operationalRevenueByDays,
    coveredOperationalRevenue,
    uncoveredOperationalRevenue,
    directDifferenceAmount,
    directDifferencePercent,
    balanceCurrent:
      n(kpis.cash_on_wb_current) ??
      n(cash.cash_on_wb_current) ??
      fallbackCurrent,
    withdrawCurrent:
      n(kpis.available_for_withdraw_current) ??
      n(cash.available_for_withdraw_current) ??
      fallbackWithdraw,
    balanceEnd: n(kpis.cash_on_wb_period_end) ?? n(cash.cash_on_wb_period_end),
    withdrawEnd:
      n(kpis.available_for_withdraw_period_end) ??
      n(cash.available_for_withdraw_period_end),
    expectedPayout: n(kpis.expected_payout) ?? n(cash.expected_payout),
    nextPayoutDate: kpis.next_payout_date ?? cash.next_payout_date ?? null,
    frozenStock: n(cash.frozen_stock_value),
    frozenPayout: n(kpis.frozen_payout) ?? n(cash.frozen_payout),
    wbDebt: n(kpis.wb_debt ?? kpis.debt) ?? n(cash.wb_debt ?? cash.debt),
    unallocatedExpenses:
      n(expenses.unallocated_expenses) ??
      n(kpis.unallocated_expenses ?? kpis.account_level_expenses) ??
      (unlinkedReportTotal || null),
    adSpendSourceLabel: adSpendSourceLabel(kpis.ad_spend_source),
    profitConfidence: profitConfidenceLabel(kpis.profit_confidence),
    expenseTotals,
    expenseComposition,
    dailyExpenseData,
    operationalDailyData,
    balanceData,
  };
}

function computeReportCoverage(
  reports: any[],
  dateFrom: string,
  dateTo: string,
): ReportCoverage {
  const selected: DateRange = { from: dateFrom, to: dateTo };
  const periods = reports
    .map(readReportPeriod)
    .filter((period): period is DateRange => Boolean(period));

  const selectedLabel = `${formatDate(dateFrom)} - ${formatDate(dateTo)}`;
  const selectedDays = daysInclusive(selected);
  if (!periods.length) {
    return {
      label: "отчеты WB не найдены",
      aligned: false,
      selected,
      periods: [],
      merged: [],
      selectedDays,
      coveredSelectedDays: 0,
      uncoveredSelectedDays: selectedDays,
      extraReportDays: 0,
      selectedCoveragePercent: 0,
      coveredSelectedLabel: "нет покрытия",
      uncoveredRangesLabel: formatRanges([selected]),
      extraRangesLabel: "нет",
      note: `Выбран период ${selectedLabel}, но закрытые финансовые отчеты WB за него не найдены. Операционную выручку можно смотреть, а финальную сверку лучше не закрывать.`,
    };
  }

  const merged = mergePeriods(periods);
  const selectedIntersections = intersectRanges(selected, merged);
  const uncoveredRanges = subtractRanges(selected, merged);
  const reportExtraRanges = merged.flatMap((period) =>
    subtractRanges(period, [selected]),
  );
  const minFrom = merged[0].from;
  const maxTo = merged.reduce(
    (max, period) => (period.to > max ? period.to : max),
    merged[0].to,
  );
  const coverageLabel = `${formatDate(minFrom)} - ${formatDate(maxTo)}`;
  const coveredSelectedDays = sumNumbers(
    selectedIntersections.map(daysInclusive),
  );
  const uncoveredSelectedDays = sumNumbers(uncoveredRanges.map(daysInclusive));
  const extraReportDays = sumNumbers(reportExtraRanges.map(daysInclusive));
  const selectedCoveragePercent =
    selectedDays > 0 ? (coveredSelectedDays / selectedDays) * 100 : 0;
  const aligned = uncoveredSelectedDays === 0;
  const hasGaps = merged.length > 1;

  return {
    label: hasGaps ? `${coverageLabel}, есть разрывы` : coverageLabel,
    aligned,
    selected,
    periods,
    merged,
    selectedDays,
    coveredSelectedDays,
    uncoveredSelectedDays,
    extraReportDays,
    selectedCoveragePercent,
    coveredSelectedLabel: formatRanges(selectedIntersections),
    uncoveredRangesLabel: formatRanges(uncoveredRanges),
    extraRangesLabel: formatRanges(reportExtraRanges),
    note: aligned
      ? `Закрытые отчеты WB покрывают выбранный период ${selectedLabel}. Операционную выручку и подтверждение WB можно сверять как один бухгалтерский контур.`
      : `Выбран период ${selectedLabel}, а закрытые отчеты WB покрывают ${coverageLabel}${hasGaps ? " с разрывами" : ""}. Поэтому операционная выручка за период и подтвержденная сумма WB могут отличаться; финальный вывод делайте после загрузки отчетов WB за весь период.`,
  };
}

type DateRange = { from: string; to: string };
type ReportCoverage = {
  label: string;
  aligned: boolean;
  selected: DateRange;
  periods: DateRange[];
  merged: DateRange[];
  selectedDays: number;
  coveredSelectedDays: number;
  uncoveredSelectedDays: number;
  extraReportDays: number;
  selectedCoveragePercent: number;
  coveredSelectedLabel: string;
  uncoveredRangesLabel: string;
  extraRangesLabel: string;
  note: string;
};

function readReportPeriod(report: any): DateRange | null {
  const from = dateText(
    report?.date_from,
    report?.period_from,
    report?.period_start,
  );
  const to = dateText(report?.date_to, report?.period_to, report?.period_end);
  return from && to ? { from, to } : null;
}

function dateText(...values: any[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      const iso = value.trim().slice(0, 10);
      if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
    }
  }
  return null;
}

function mergePeriods(periods: DateRange[]): DateRange[] {
  const sorted = [...periods].sort((a, b) => a.from.localeCompare(b.from));
  const merged: DateRange[] = [];
  for (const period of sorted) {
    const last = merged[merged.length - 1];
    if (!last || period.from > addDaysIso(last.to, 1)) {
      merged.push({ ...period });
      continue;
    }
    if (period.to > last.to) last.to = period.to;
  }
  return merged;
}

function intersectRanges(range: DateRange, periods: DateRange[]): DateRange[] {
  return periods
    .map((period) => ({
      from: maxIso(range.from, period.from),
      to: minIso(range.to, period.to),
    }))
    .filter((period) => period.from <= period.to);
}

function subtractRanges(range: DateRange, periods: DateRange[]): DateRange[] {
  const overlaps = intersectRanges(range, mergePeriods(periods));
  const result: DateRange[] = [];
  let cursor = range.from;
  for (const overlap of overlaps) {
    if (cursor < overlap.from) {
      result.push({ from: cursor, to: addDaysIso(overlap.from, -1) });
    }
    cursor = addDaysIso(overlap.to, 1);
  }
  if (cursor <= range.to) {
    result.push({ from: cursor, to: range.to });
  }
  return result;
}

function formatRanges(ranges: DateRange[]): string {
  if (!ranges.length) return "нет";
  return ranges
    .map((range) => `${formatDate(range.from)} - ${formatDate(range.to)}`)
    .join(", ");
}

function daysInclusive(range: DateRange): number {
  const from = new Date(`${range.from}T00:00:00`).getTime();
  const to = new Date(`${range.to}T00:00:00`).getTime();
  if (!Number.isFinite(from) || !Number.isFinite(to) || to < from) return 0;
  return Math.floor((to - from) / 86_400_000) + 1;
}

function rangeDays(range: DateRange): string[] {
  const result: string[] = [];
  let cursor = range.from;
  while (cursor <= range.to && result.length < 370) {
    result.push(cursor);
    cursor = addDaysIso(cursor, 1);
  }
  return result;
}

function maxIso(a: string, b: string): string {
  return a > b ? a : b;
}

function minIso(a: string, b: string): string {
  return a < b ? a : b;
}

function isDateInRanges(date: string, ranges: DateRange[]): boolean {
  return ranges.some((range) => date >= range.from && date <= range.to);
}

function sumNumbers(values: number[]): number {
  return values.reduce(
    (sum, value) => sum + (Number.isFinite(value) ? value : 0),
    0,
  );
}

function addDaysIso(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + days);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function ledgerTotals(rows: any[]) {
  return rows.reduce(
    (acc, row) => {
      acc.retail += n(row.retail_amount ?? row.amount) ?? 0;
      acc.forPay += n(row.for_pay ?? row.ppvz_for_pay) ?? 0;
      acc.commission +=
        n(
          row.ppvz_sales_commission ?? row.commission_amount ?? row.commission,
        ) ?? 0;
      acc.logistics += rowLogistics(row);
      acc.adjustments +=
        (n(row.penalty) ?? 0) +
        (n(row.deduction) ?? 0) +
        (n(row.return_amount) ?? 0);
      return acc;
    },
    { retail: 0, forPay: 0, commission: 0, logistics: 0, adjustments: 0 },
  );
}

function rowsFrom(data: any): any[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  if (Array.isArray(data.items)) return data.items;
  if (Array.isArray(data.rows)) return data.rows;
  if (Array.isArray(data.articles)) return data.articles;
  return [];
}

function pageTotal(data: any): number | null {
  return data && !Array.isArray(data) && typeof data.total === "number"
    ? data.total
    : null;
}

function n(value: any): number | null {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function moneyDash(value: any): string {
  const parsed = n(value);
  return parsed == null ? "—" : formatMoney(parsed);
}

function dash(value: any): ReactNode {
  return value == null || value === "" ? "—" : value;
}

function rowDelta(row: any): number {
  const explicit = n(row.revenue_delta);
  if (explicit != null) return explicit;
  return (
    (n(row.sale_revenue ?? row.order_revenue ?? row.operational_revenue) ?? 0) -
    (n(row.finance_revenue) ?? 0)
  );
}

function rowLogistics(row: any): number {
  return (
    (n(row.delivery_service) ?? 0) +
    (n(row.rebill_logistic_cost) ?? 0) +
    (n(row.delivery_amount) ?? 0)
  );
}

function uniq(values: any[]): string[] {
  return Array.from(
    new Set(
      values.filter((value) => value != null && value !== "").map(String),
    ),
  ).sort((a, b) => a.localeCompare(b));
}

function shortDate(value: any): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}

function statusLabel(status: string): string {
  switch (String(status).toLowerCase()) {
    case "matched":
    case "closed":
      return "Сверено";
    case "mismatch":
      return "Есть расхождения";
    case "critical_mismatch":
      return "Критические расхождения";
    case "missing_finance":
      return "Нет в финансовом отчете WB";
    case "missing_sale":
      return "Нет в продажах";
    case "order_without_followup":
      return "Заказ без продолжения";
    case "not_available":
      return "Нет отчета";
    default:
      return status || "—";
  }
}

function qualityLabel(value: string): string {
  switch (value) {
    case "complete":
      return "полное";
    case "unclassified_present":
      return "есть неразнесенное";
    case "ad_double_count_risk":
      return "риск дубля рекламы";
    case "partial":
      return "частично";
    default:
      return "требует проверки";
  }
}

function adSpendSourceLabel(value: any): string {
  switch (String(value ?? "")) {
    case "finance_report":
      return "из финансового отчета WB";
    case "ads_api":
      return "из рекламного API";
    case "manual":
      return "введено вручную";
    case "":
      return "выбрано автоматически";
    default:
      return "выбрано автоматически";
  }
}

function profitConfidenceLabel(value: any): string {
  switch (String(value ?? "")) {
    case "final":
    case "high":
    case "complete":
      return "Высокая уверенность";
    case "medium":
    case "partial":
      return "Частично подтверждено";
    case "low":
      return "Нужна проверка";
    case "":
      return "Не оценено";
    default:
      return "Не оценено";
  }
}
