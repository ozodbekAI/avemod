/* eslint-disable @typescript-eslint/ban-ts-comment, @typescript-eslint/no-explicit-any */
// @ts-nocheck
// /money is a UI route. Backend calls stay under /api/v1/money/*.

import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  BarChart3,
  Boxes,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  ClipboardList,
  Coins,
  FileText,
  Layers,
  Megaphone,
  Package,
  ReceiptText,
  RefreshCw,
  ShieldAlert,
  Truck,
  Wallet,
} from "lucide-react";

import { EndpointError } from "@/components/EndpointError";
import { ExportButton } from "@/components/ExportButton";
import { ApiErrorState, EmptyState } from "@/components/money-ui";
import { MoneyTrustChipStrip } from "@/components/finance/MoneyTrustChipStrip";
import { isFinanceBlocker } from "@/components/finance/financeCategorize";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAccounts } from "@/lib/account-context";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { evidenceFrom } from "@/lib/evidence";
import {
  formatDateTime,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
} from "@/lib/format";
import {
  fetchDataBlockers,
  fetchMoneyActionsToday,
  fetchMoneyArticles,
} from "@/lib/money-endpoints";
import { isSellerVisibleMoneyTrust, moneyTrustFrom } from "@/lib/money-trust";
import {
  expensesBreakdownQueryOptions,
  profitCascadeQueryOptions,
  categoryLabel,
} from "@/lib/queries/expenses";
import { moneySummaryQueryOptions } from "@/lib/queries/money-summary";
import { useStrictFinal } from "@/lib/queries/strict-final";
import { normalizeTrust } from "@/lib/trust";
import { cn } from "@/lib/utils";
import { useDateRange } from "@/lib/date-range-context";
import type { MMoneySummary } from "@/lib/api";

export const Route = createFileRoute("/_authenticated/money")({
  component: MoneyPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

type Tone = "good" | "warn" | "bad" | "info" | "neutral";
type DetailRow = {
  label: string;
  value: number | string | null | undefined;
  op?: "+" | "-" | "=" | "info";
  note?: string | null;
  href?: string | null;
  tone?: Tone;
};
type Drilldown = {
  title: string;
  value?: number | string | null;
  subtitle?: string | null;
  tone?: Tone;
  formula?: string | null;
  rows?: DetailRow[];
  sources?: string[];
  cta?: { label: string; to: string } | null;
};

const PERIODS = [
  { id: "7", label: "7д", days: 7 },
  { id: "30", label: "30д", days: 30 },
  { id: "90", label: "90д", days: 90 },
] as const;

const EXPENSE_CATEGORY_LABELS: Record<string, string> = {
  wb_commission: "Комиссия WB",
  payment_processing: "Эквайринг",
  pvz_reward: "ПВЗ",
  wb_logistics: "Логистика WB",
  wb_logistics_rebill: "Перевыставленная логистика",
  storage: "Хранение",
  acceptance: "Приемка",
  penalty: "Штрафы",
  deduction: "Удержания",
  marketing_deduction: "Продвижение WB",
  loyalty: "Лояльность",
  seller_cogs: "Себестоимость",
  seller_other_expense: "Прочие расходы продавца",
  ads_operational: "Реклама",
  unclassified: "Неклассифицированные",
};

const MONEY_SOURCE_LABELS: Record<string, string> = {
  finance_report: "Финансовый отчёт WB",
  finance_reports: "Финансовый отчёт WB",
  finance_balance: "Баланс WB",
  money_summary: "Сводка денег",
  profit_cascade: "Расчёт прибыли",
  expenses_breakdown: "Детализация расходов",
  costs: "Себестоимость",
  cost: "Себестоимость",
  stocks: "Остатки WB",
  stock: "Остатки WB",
  ads: "Реклама WB",
  wb_api: "Wildberries API",
  manual: "Вручную",
  operations: "Операционные данные",
};

const MONEY_PATH_LABELS: Record<string, string> = {
  "/money/summary": "Сводка денег",
  "/finance/reports": "Финансовый отчёт WB",
  "/finance/balance": "Баланс WB",
  "/money/expenses/breakdown": "Детализация расходов",
  "/money/profit-cascade": "Расчёт прибыли",
  "/costs": "Себестоимость",
  "/stocks": "Остатки WB",
  "/ads": "Реклама WB",
};

const MONEY_VALUE_LABELS: Record<string, string> = {
  critical_mismatch: "Критичное расхождение",
  mismatch: "Есть расхождение",
  matched: "Сверено",
  final: "Финально",
  operational: "Операционно",
  provisional: "Предварительно",
  operational_provisional: "Операционно, не финально",
  missing: "Нет данных",
  unavailable: "Нет данных",
  finance_report: "Финансовый отчёт WB",
};

function MoneyPage() {
  const { activeId } = useAccounts();
  const dr = useDateRange();
  const range = { from: dr.from, to: dr.to };
  const setRange = (next: { from: string; to: string }) =>
    dr.setRange(next.from, next.to);
  const enabled = !!activeId;
  const baseParams = activeId
    ? { accountId: activeId, dateFrom: range.from, dateTo: range.to }
    : null;
  const [detail, setDetail] = useState<Drilldown | null>(null);

  const sumQ = useQuery<MMoneySummary>(
    moneySummaryQueryOptions({
      accountId: activeId,
      dateFrom: range.from,
      dateTo: range.to,
    }),
  );

  const todayQ = useQuery<any>({
    queryKey: ["money-actions-today", activeId, range.from, range.to],
    enabled,
    queryFn: () => fetchMoneyActionsToday({ ...baseParams!, limit: 10 }),
    staleTime: 2 * 60 * 1000,
  });

  const blockersQ = useQuery<any>({
    queryKey: ["money-data-blockers", activeId, range.from, range.to],
    enabled,
    queryFn: () => fetchDataBlockers(baseParams!),
    staleTime: 2 * 60 * 1000,
  });

  const articlesQ = useQuery<any>({
    queryKey: ["money-articles-top", activeId, range.from, range.to],
    enabled,
    queryFn: () => fetchMoneyArticles({ ...baseParams!, limit: 10 }),
    staleTime: 2 * 60 * 1000,
    placeholderData: (prev: any) => prev,
  });

  const breakdownQ = useQuery(
    expensesBreakdownQueryOptions({
      accountId: activeId,
      dateFrom: range.from,
      dateTo: range.to,
    }),
  );
  const cascadeQ = useQuery(
    profitCascadeQueryOptions({
      accountId: activeId,
      dateFrom: range.from,
      dateTo: range.to,
    }),
  );

  const s = sumQ.data;
  const k = s?.kpis as any;
  const meta = s?.meta;
  const quality = (s as any)?.quality;
  const financeReconciliation = (s as any)?.finance_reconciliation;
  const revenueSources = (s as any)?.revenue_sources;
  const businessStatus = pickStr(s?.answer, "business_status");
  const financeStatus =
    pickStr(s as any, "finance_reconciliation_status") ??
    pickStr(k, "finance_reconciliation_status") ??
    pickStr(quality, "finance_reconciliation_status") ??
    pickStr(financeReconciliation, "status") ??
    pickStr(revenueSources, "reconciliation_status");
  const financeDiffPct =
    pickNum(s as any, "finance_difference_percent") ??
    pickNum(k, "finance_difference_percent") ??
    pickNum(quality, "finance_difference_percent") ??
    pickNum(financeReconciliation, "difference_percent") ??
    pickNum(revenueSources, "difference_percent");
  const financeDiffAmount =
    pickNum(k, "finance_difference_amount", "finance_revenue_diff") ??
    pickNum(s as any, "finance_difference_amount", "finance_revenue_diff") ??
    pickNum(quality, "finance_difference_amount") ??
    pickNum(financeReconciliation, "difference_amount") ??
    pickNum(revenueSources, "difference_amount");
  const supplierCoverage = pickNum(
    k,
    "supplier_confirmed_revenue_coverage_percent",
    "supplier_cost_coverage_percent",
    "supplier_cost_confirmed_revenue_percent",
  );
  const adsOverallocated = pickNum(
    k,
    "ads_overallocated_spend",
    "ads_unallocated_spend",
  );
  const adsAllocationStatus = pickStr(k, "ads_allocation_status");
  const strict = useStrictFinal({
    accountId: activeId,
    dateFrom: range.from,
    dateTo: range.to,
  });
  const financialFinal = strict.financialFinalUi
    ? true
    : strict.dataHealth || strict.dqSummary
      ? false
      : normalizeTrust(s).financialFinal;
  const finalProfitBlockers =
    pickNum(
      blockersQ.data,
      "final_profit_blockers_total",
      "financial_final_blockers_total",
      "blocking_open_issues_total",
    ) ??
    pickNum(
      blockersQ.data?.data_quality_summary,
      "final_profit_blockers_total",
      "financial_final_blockers_total",
      "blocking_open_issues_total",
    ) ??
    strict.finalBlockers ??
    null;
  const openIssues =
    pickNum(blockersQ.data, "open_issues_total", "issues_total") ??
    pickNum(
      blockersQ.data?.data_quality_summary,
      "open_issues_total",
      "all_open_issues_total",
    ) ??
    (Array.isArray(blockersQ.data?.issues)
      ? blockersQ.data.issues.length
      : null);
  const isProvisional =
    businessStatus === "provisional" ||
    businessStatus === "operational_provisional" ||
    financialFinal === false;

  const cogs = useMemo(() => {
    return (
      pickNum(k, "seller_cogs", "estimated_cogs") ??
      pickNum(cascadeQ.data?.cascade?.totals, "seller_cogs") ??
      pickNum(breakdownQ.data, "seller_cogs")
    );
  }, [k, cascadeQ.data, breakdownQ.data]);

  const sellerOtherExpense = useMemo(() => {
    return (
      pickNum(k, "seller_other_expense") ??
      pickNum(cascadeQ.data?.cascade?.totals, "seller_other_expense") ??
      pickNum(breakdownQ.data, "seller_other_expense")
    );
  }, [k, cascadeQ.data, breakdownQ.data]);

  const directWbExpenses = useMemo(() => {
    const explicit = pickNum(k, "direct_wb_expenses");
    if (explicit != null) return explicit;
    const wb = pickNum(k, "wb_expenses_total");
    const unallocated = pickNum(
      k,
      "unallocated_expenses",
      "account_level_expenses",
    );
    if (wb == null) return null;
    return unallocated == null ? wb : Math.max(0, wb - unallocated);
  }, [k]);

  const financeOperationalRevenue =
    pickNum(financeReconciliation, "operational_revenue") ??
    pickNum(revenueSources, "operational_revenue", "comparison_mart_revenue");
  const netProfitValue =
    k?.net_profit_after_all_expenses ??
    cascadeQ.data?.cascade?.totals?.net_profit_after_all_expenses ??
    k?.net_profit_after_ads ??
    null;
  const ownerProfit = useMemo(() => {
    const p = k?.net_profit_after_ads ?? null;
    const u = k?.unallocated_expenses ?? null;
    if (p == null) return netProfitValue ?? null;
    return p - (u ?? 0);
  }, [k, netProfitValue]);
  const ownerMargin = useMemo(() => {
    const revenue = k?.revenue ?? null;
    if (ownerProfit == null || revenue == null || !revenue) return null;
    return (ownerProfit / revenue) * 100;
  }, [ownerProfit, k]);

  const evidenceFor = (...keys: string[]) => {
    for (const key of keys) {
      const ledger = evidenceFrom(
        k?.evidence_ledger?.[key],
        (s as any)?.evidence_ledger?.[key],
      );
      if (ledger) return ledger;
    }
    return null;
  };

  const breakdownItems = useMemo(
    () =>
      normalizeExpenseItems(breakdownQ.data ?? (s as any)?.expense_breakdown),
    [breakdownQ.data, s],
  );
  const cascadeGroups = useMemo(
    () =>
      normalizeCascadeGroups(
        cascadeQ.data ?? (s as any)?.profit_cascade,
        breakdownItems,
      ),
    [cascadeQ.data, s, breakdownItems],
  );
  const articles = useMemo(
    () => normalizeArticles(articlesQ.data),
    [articlesQ.data],
  );
  const blockers = useMemo(
    () => normalizeBlockers(blockersQ.data),
    [blockersQ.data],
  );
  const actions = useMemo(() => normalizeActions(todayQ.data), [todayQ.data]);
  const financeBlockers = blockers.filter((b: any) =>
    isFinanceBlocker(b?.code),
  );

  const pnlRows = useMemo(() => {
    const additionalIncome =
      pickNum(k, "additional_income") ??
      pickNum(cascadeQ.data?.cascade?.totals, "additional_income");
    return [
      {
        key: "revenue",
        label: "Выручка",
        value: k?.revenue ?? null,
        icon: CircleDollarSign,
        tone: "good" as Tone,
        sign: "+",
        detail: {
          title: "Выручка",
          value: k?.revenue ?? null,
          subtitle: financialFinal ? "финально" : "операционно",
          formula:
            "Операционная выручка. Финансовая сверка показывается отдельно.",
          rows: [
            {
              label: "Операционная выручка",
              value: k?.revenue ?? null,
              op: "+",
            },
            {
              label: "Для фин. сверки",
              value: financeOperationalRevenue,
              op: "info",
            },
            {
              label: "Подтверждено финансами WB",
              value: k?.finance_confirmed_revenue ?? null,
              op: "info",
            },
            {
              label: "Разница финансы WB / операции",
              value: financeDiffAmount,
              op: "info",
              note:
                financeDiffPct != null ? formatPercent(financeDiffPct) : null,
            },
          ],
          sources: ["/money/summary", "/finance/reports"],
        },
      },
      {
        key: "wb",
        label: "WB расходы",
        value: directWbExpenses,
        icon: ReceiptText,
        tone: "bad" as Tone,
        sign: "-",
        detail: expenseDetailFromGroup(
          "WB расходы",
          directWbExpenses,
          cascadeGroups,
          breakdownItems,
          ["wb_direct_expenses", "wb_expenses", "other_wb_expenses"],
          "/expenses",
        ),
      },
      {
        key: "cogs",
        label: "Себестоимость",
        value: cogs,
        icon: Package,
        tone: "bad" as Tone,
        sign: "-",
        detail: {
          title: "Себестоимость",
          value: cogs,
          subtitle:
            supplierCoverage != null
              ? `покрытие ${supplierCoverage.toFixed(0)}%`
              : null,
          formula:
            "Себестоимость товара по подтвержденным или операционным данным.",
          rows: [
            { label: "Себестоимость", value: cogs, op: "-" },
            {
              label: "Покрытие себестоимости",
              value:
                supplierCoverage == null
                  ? null
                  : `${supplierCoverage.toFixed(0)}%`,
              op: "info",
            },
          ],
          sources: ["/money/summary", "/costs"],
          cta: { label: "Открыть себестоимость", to: "/costs" },
        },
      },
      {
        key: "ads",
        label: "Реклама",
        value: k?.ad_spend ?? null,
        icon: Megaphone,
        tone: "bad" as Tone,
        sign: "-",
        detail: {
          title: "Реклама",
          value: k?.ad_spend ?? null,
          subtitle: adsAllocationStatus ?? null,
          formula: "Рекламные расходы, которые участвуют в расчете прибыли.",
          rows: [
            { label: "Реклама", value: k?.ad_spend ?? null, op: "-" },
            {
              label: "Нераспределено / сверх распределения",
              value: adsOverallocated,
              op: "info",
              tone: adsOverallocated ? "warn" : "neutral",
            },
          ],
          sources: ["/money/summary", "/ads"],
          cta: { label: "Открыть рекламу", to: "/ads" },
        },
      },
      {
        key: "seller_other",
        label: "Прочее",
        value: sumNullable(sellerOtherExpense, k?.unallocated_expenses ?? null),
        rawParts: [sellerOtherExpense, k?.unallocated_expenses ?? null],
        icon: Layers,
        tone: k?.unallocated_expenses > 0 ? ("warn" as Tone) : ("bad" as Tone),
        sign: "-",
        detail: {
          title: "Прочие и неразобранные расходы",
          value: sumNullable(
            sellerOtherExpense,
            k?.unallocated_expenses ?? null,
          ),
          subtitle: k?.unallocated_expenses > 0 ? "есть неразобранное" : null,
          formula:
            "Прочие расходы продавца + расходы аккаунта, которые еще не распределены.",
          rows: [
            {
              label: "Прочие расходы продавца",
              value: sellerOtherExpense,
              op: "-",
            },
            {
              label: "Нераспределенные расходы",
              value: k?.unallocated_expenses ?? null,
              op: "-",
              tone: k?.unallocated_expenses > 0 ? "warn" : "neutral",
            },
          ],
          sources: ["/money/summary", "/money/expenses/breakdown"],
          cta: { label: "Открыть расходы", to: "/expenses" },
        },
      },
      {
        key: "additional",
        label: "Доплаты",
        value: additionalIncome,
        icon: Coins,
        tone: "good" as Tone,
        sign: "+",
        optional: true,
        detail: {
          title: "Доплаты и компенсации",
          value: additionalIncome,
          formula: "Положительные корректировки из финансовых данных.",
          rows: [{ label: "Доплаты", value: additionalIncome, op: "+" }],
          sources: ["/money/summary", "/money/profit-cascade"],
        },
      },
    ].filter((row) => !row.optional || row.value != null);
  }, [
    k,
    cogs,
    directWbExpenses,
    sellerOtherExpense,
    supplierCoverage,
    financeOperationalRevenue,
    financeDiffAmount,
    financeDiffPct,
    financialFinal,
    adsAllocationStatus,
    adsOverallocated,
    cascadeGroups,
    breakdownItems,
    cascadeQ.data,
  ]);

  const locations = useMemo(
    () => [
      {
        key: "wb_cash",
        label: "Баланс WB",
        value: k?.cash_on_wb ?? null,
        icon: Wallet,
        tone: "good" as Tone,
        detail: {
          title: "Баланс WB",
          value: k?.cash_on_wb ?? null,
          formula: "Текущий снимок денег на WB.",
          rows: [
            { label: "Баланс WB", value: k?.cash_on_wb ?? null, op: "=" },
            {
              label: "Доступно к выводу",
              value: k?.available_for_withdraw ?? null,
              op: "info",
            },
            { label: "К выплате", value: k?.for_pay ?? null, op: "info" },
          ],
          sources: ["/money/summary", "/finance/balance"],
        },
      },
      {
        key: "withdraw",
        label: "Доступно к выводу",
        value: k?.available_for_withdraw ?? null,
        icon: Banknote,
        tone: "good" as Tone,
        detail: {
          title: "Доступно к выводу",
          value: k?.available_for_withdraw ?? null,
          rows: [
            {
              label: "Доступно к выводу",
              value: k?.available_for_withdraw ?? null,
              op: "=",
            },
            { label: "Баланс WB", value: k?.cash_on_wb ?? null, op: "info" },
          ],
          sources: ["/finance/balance"],
        },
      },
      {
        key: "for_pay",
        label: "К выплате",
        value: k?.for_pay ?? null,
        icon: Coins,
        tone: "info" as Tone,
        detail: {
          title: "К выплате",
          value: k?.for_pay ?? null,
          rows: [{ label: "К выплате", value: k?.for_pay ?? null, op: "=" }],
          sources: ["/money/summary", "/finance/reports"],
        },
      },
      {
        key: "stock",
        label: "В товаре",
        value: k?.stock_value ?? null,
        icon: Boxes,
        tone: "info" as Tone,
        detail: {
          title: "Деньги в товаре",
          value: k?.stock_value ?? null,
          subtitle: k?.stock_value_confidence
            ? `точность: ${k.stock_value_confidence}`
            : null,
          formula:
            "Остатки × себестоимость. Если себестоимости нет, ноль не подставляется.",
          rows: [
            {
              label: "Стоимость остатка",
              value: k?.stock_value ?? null,
              op: "=",
            },
            {
              label: "Сверхзапас",
              value: k?.overstock_value ?? null,
              op: "info",
              tone: k?.overstock_value > 0 ? "warn" : "neutral",
            },
            { label: "В пути", value: k?.in_transit_value ?? null, op: "info" },
          ],
          sources: ["/money/summary", "/stocks", "/costs"],
        },
      },
      {
        key: "transit",
        label: "В пути",
        value: k?.in_transit_value ?? null,
        icon: Truck,
        tone: "info" as Tone,
        detail: {
          title: "Товар в пути",
          value: k?.in_transit_value ?? null,
          rows: [
            {
              label: "Товар в пути",
              value: k?.in_transit_value ?? null,
              op: "=",
            },
          ],
          sources: ["/money/summary", "/stocks"],
        },
      },
      {
        key: "overstock",
        label: "Сверхзапас",
        value: k?.overstock_value ?? null,
        icon: Package,
        tone: k?.overstock_value > 0 ? ("warn" as Tone) : ("neutral" as Tone),
        detail: {
          title: "Сверхзапас",
          value: k?.overstock_value ?? null,
          subtitle: k?.overstock_value > 0 ? "замороженные деньги" : null,
          rows: [
            { label: "Сверхзапас", value: k?.overstock_value ?? null, op: "=" },
            {
              label: "Всего в товаре",
              value: k?.stock_value ?? null,
              op: "info",
            },
          ],
          sources: ["/money/summary", "/stocks"],
        },
      },
    ],
    [k],
  );

  const totalTrackedMoney = useMemo(
    () => locations.reduce((sum, item) => sum + positive(item.value), 0),
    [locations],
  );

  return (
    <div className="min-h-screen bg-background">
      <MoneyDeskHeader
        range={range}
        onRangeChange={setRange}
        onRefresh={() => sumQ.refetch()}
        isRefreshing={sumQ.isFetching}
        lastUpdated={
          sumQ.dataUpdatedAt ? new Date(sumQ.dataUpdatedAt).toISOString() : null
        }
        activeId={activeId}
        rightSlot={
          <MoneyTrustChipStrip
            hasConfirmedFinance={k?.finance_confirmed_revenue != null}
            hasProvisional={
              k?.revenue != null || k?.net_profit_after_ads != null
            }
            hasEstimate={k?.stock_value != null || k?.overstock_value != null}
            hasMissing={
              k?.finance_confirmed_revenue == null ||
              k?.stock_value == null ||
              k?.cash_on_wb == null
            }
            hasOpportunity={financeBlockers.length > 0}
            hasTestOnly={false}
          />
        }
      />

      {!activeId ? (
        <div className="px-6 py-8 text-sm text-muted-foreground">
          Сначала выберите аккаунт.
        </div>
      ) : sumQ.isLoading ? (
        <MoneyPageSkeleton />
      ) : sumQ.isError ? (
        <div className="px-6 py-6">
          <ApiErrorState
            error={sumQ.error}
            endpoint="/money/summary"
            onRetry={() => sumQ.refetch()}
            title="Не удалось загрузить /money/summary"
          />
        </div>
      ) : !s ? (
        <div className="px-6 py-6">
          <EmptyState onRetry={() => sumQ.refetch()} />
        </div>
      ) : (
        <main className="w-full px-4 py-4 sm:px-5 space-y-4">
          <ReliabilityStrip
            financialFinal={financialFinal}
            financeStatus={financeStatus}
            financeDiffPct={financeDiffPct}
            supplierCoverage={supplierCoverage}
            finalProfitBlockers={finalProfitBlockers}
            openIssues={openIssues}
            onOpen={setDetail}
          />

          <section className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_400px] 2xl:grid-cols-[minmax(0,1fr)_420px]">
            <div className="min-w-0 space-y-3">
              <ProfitFlowPanel
                revenue={k?.revenue ?? null}
                financeConfirmedRevenue={k?.finance_confirmed_revenue ?? null}
                financeDiffAmount={financeDiffAmount}
                financeDiffPct={financeDiffPct}
                netProfit={netProfitValue}
                ownerProfit={ownerProfit}
                ownerMargin={ownerMargin}
                unallocatedExpenses={k?.unallocated_expenses ?? null}
                financialFinal={financialFinal}
                isProvisional={isProvisional}
                rows={pnlRows}
                onOpen={setDetail}
              />

              <Tabs defaultValue="expenses" className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <TabsList className="h-8 flex-wrap justify-start">
                    <TabsTrigger value="expenses" className="h-7 gap-1.5 px-3">
                      <ReceiptText className="h-3.5 w-3.5" />
                      Расходы
                    </TabsTrigger>
                    <TabsTrigger value="positions" className="h-7 gap-1.5 px-3">
                      <Wallet className="h-3.5 w-3.5" />
                      Позиции
                    </TabsTrigger>
                    <TabsTrigger value="control" className="h-7 gap-1.5 px-3">
                      <ClipboardList className="h-3.5 w-3.5" />
                      Контроль
                    </TabsTrigger>
                    <TabsTrigger value="cards" className="h-7 gap-1.5 px-3">
                      <BarChart3 className="h-3.5 w-3.5" />
                      Карточки
                    </TabsTrigger>
                  </TabsList>
                  <ExportButton
                    endpoint={API_ENDPOINTS.exports.profitBySku}
                    filenamePrefix="profit_by_sku"
                    query={{
                      account_id: activeId,
                      date_from: range.from,
                      date_to: range.to,
                    }}
                    label="Экспорт SKU"
                  />
                </div>

                <TabsContent value="expenses" className="mt-0">
                  <ExpensesWorkspace
                    groups={cascadeGroups}
                    items={breakdownItems}
                    summary={
                      breakdownQ.data ?? (s as any)?.expense_breakdown ?? null
                    }
                    isLoading={breakdownQ.isLoading}
                    onOpen={setDetail}
                    dateFrom={range.from}
                    dateTo={range.to}
                  />
                </TabsContent>
                <TabsContent value="positions" className="mt-0">
                  <PositionsWorkspace
                    locations={locations}
                    evidenceFor={evidenceFor}
                    onOpen={setDetail}
                  />
                </TabsContent>
                <TabsContent value="control" className="mt-0">
                  <ControlWorkspace
                    actions={actions}
                    blockers={blockers}
                    financeBlockers={financeBlockers}
                    isActionsLoading={todayQ.isLoading}
                    isBlockersLoading={blockersQ.isLoading}
                    actionsError={todayQ.error}
                    blockersError={blockersQ.error}
                    actionsIsError={todayQ.isError}
                    blockersIsError={blockersQ.isError}
                    onRetryActions={() => todayQ.refetch()}
                    onRetryBlockers={() => blockersQ.refetch()}
                  />
                </TabsContent>
                <TabsContent value="cards" className="mt-0">
                  <ArticlesWorkspace
                    articles={articles}
                    isLoading={articlesQ.isLoading}
                    financeDiffAmount={financeDiffAmount}
                    financeDiffPct={financeDiffPct}
                    financeStatus={financeStatus}
                  />
                </TabsContent>
              </Tabs>
            </div>

            <div className="space-y-3">
              <MoneyLocationsPanel
                locations={locations}
                total={totalTrackedMoney}
                onOpen={setDetail}
              />
              <WbControlPanel
                summary={
                  breakdownQ.data ?? (s as any)?.expense_breakdown ?? null
                }
                onOpen={setDetail}
              />
            </div>
          </section>

          <DetailSheet
            detail={detail}
            onOpenChange={(open) => !open && setDetail(null)}
          />
        </main>
      )}
    </div>
  );
}

function MoneyDeskHeader({
  range,
  onRangeChange,
  onRefresh,
  isRefreshing,
  lastUpdated,
  activeId,
  rightSlot,
}: {
  range: { from: string; to: string };
  onRangeChange: (next: { from: string; to: string }) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  lastUpdated: string | null;
  activeId: number | null | undefined;
  rightSlot?: React.ReactNode;
}) {
  return (
    <header className="border-b bg-card/80">
      <div className="w-full px-4 py-3 sm:px-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">Деньги</h1>
              <Badge variant="outline" className="gap-1 text-[11px]">
                <CircleDollarSign className="h-3 w-3" />
                карта денег
              </Badge>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>Аккаунт: {activeId ?? "—"}</span>
              {lastUpdated ? (
                <span>Обновлено: {formatDateTime(lastUpdated)}</span>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <div className="flex h-9 items-center rounded-md border bg-background p-1">
              {PERIODS.map((p) => (
                <Button
                  key={p.id}
                  size="sm"
                  variant={isSameRange(range, p.days) ? "default" : "ghost"}
                  className="h-7 px-2.5"
                  onClick={() => onRangeChange(rangeForDays(p.days))}
                >
                  {p.label}
                </Button>
              ))}
            </div>
            <div className="flex items-center gap-2 rounded-md border bg-background px-2 py-1">
              <CalendarDays className="h-4 w-4 text-muted-foreground" />
              <Input
                type="date"
                value={range.from}
                onChange={(e) =>
                  onRangeChange({ ...range, from: e.target.value })
                }
                className="h-7 w-[136px] border-0 px-1 shadow-none focus-visible:ring-0"
              />
              <span className="text-muted-foreground">-</span>
              <Input
                type="date"
                value={range.to}
                onChange={(e) =>
                  onRangeChange({ ...range, to: e.target.value })
                }
                className="h-7 w-[136px] border-0 px-1 shadow-none focus-visible:ring-0"
              />
            </div>
            <Button
              variant="outline"
              size="icon"
              onClick={onRefresh}
              disabled={isRefreshing}
              title="Обновить"
            >
              <RefreshCw
                className={cn("h-4 w-4", isRefreshing && "animate-spin")}
              />
            </Button>
            {rightSlot}
          </div>
        </div>
      </div>
    </header>
  );
}

function ReliabilityStrip({
  financialFinal,
  financeStatus,
  financeDiffPct,
  supplierCoverage,
  finalProfitBlockers,
  openIssues,
  onOpen,
}: {
  financialFinal: boolean | null;
  financeStatus: string | null;
  financeDiffPct: number | null;
  supplierCoverage: number | null;
  finalProfitBlockers: number | null;
  openIssues: number | null;
  onOpen: (d: Drilldown) => void;
}) {
  const items = [
    {
      label: "Финал",
      value: financialFinal ? "закрыто" : "операц.",
      tone: financialFinal ? "good" : "warn",
      icon: CheckCircle2,
      detail: {
        title: "Статус финальности",
        value: financialFinal ? "финально" : "предварительно",
        rows: [
          {
            label: "Финальная прибыль",
            value: financialFinal ? "да" : "нет",
            op: "info",
          },
          { label: "Статус сверки", value: financeStatus ?? "—", op: "info" },
          {
            label: "Блокеры финальной прибыли",
            value: finalProfitBlockers,
            op: "info",
            tone: finalProfitBlockers ? "warn" : "good",
          },
        ],
      },
    },
    {
      label: "Сверка WB",
      value: financeDiffPct == null ? "—" : formatPercent(financeDiffPct),
      tone:
        financeStatus === "critical_mismatch" ||
        Math.abs(financeDiffPct ?? 0) > 3
          ? "bad"
          : "good",
      icon: FileText,
      detail: {
        title: "Сверка с финансовым отчетом WB",
        value:
          financeDiffPct == null ? null : `${formatPercent(financeDiffPct)}`,
        rows: [
          { label: "Статус", value: financeStatus ?? "—", op: "info" },
          {
            label: "Расхождение",
            value:
              financeDiffPct == null
                ? null
                : `${formatPercent(financeDiffPct)}`,
            op: "info",
          },
        ],
        cta: { label: "Открыть финансы", to: "/finance" },
      },
    },
    {
      label: "Себестоимость",
      value: supplierCoverage == null ? "—" : `${supplierCoverage.toFixed(0)}%`,
      tone:
        supplierCoverage == null || supplierCoverage < 80
          ? "bad"
          : supplierCoverage < 95
            ? "warn"
            : "good",
      icon: Package,
      detail: {
        title: "Покрытие себестоимости",
        value:
          supplierCoverage == null ? null : `${supplierCoverage.toFixed(0)}%`,
        rows: [
          {
            label: "Покрытие",
            value:
              supplierCoverage == null
                ? null
                : `${supplierCoverage.toFixed(0)}%`,
            op: "info",
          },
        ],
        cta: { label: "Открыть себестоимость", to: "/costs" },
      },
    },
    {
      label: "Ошибки",
      value: String(openIssues ?? 0),
      tone:
        (finalProfitBlockers ?? 0) > 0
          ? "bad"
          : (openIssues ?? 0) > 0
            ? "warn"
            : "good",
      icon: ShieldAlert,
      detail: {
        title: "Качество данных",
        value: openIssues ?? 0,
        rows: [
          { label: "Открытых issues", value: openIssues ?? 0, op: "info" },
          {
            label: "Блокеры финальной прибыли",
            value: finalProfitBlockers ?? 0,
            op: "info",
          },
        ],
        cta: { label: "Открыть исправление", to: "/data-fix" },
      },
    },
  ];

  return (
    <section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <button
            key={item.label}
            type="button"
            onClick={() => onOpen(item.detail)}
            className={cn(
              "flex items-center justify-between gap-3 rounded-lg border bg-card px-3 py-2 text-left transition hover:bg-accent/45",
              toneBorder(item.tone),
            )}
          >
            <div className="flex min-w-0 items-center gap-2">
              <span
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
                  toneSoft(item.tone),
                )}
              >
                <Icon className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <div className="truncate text-xs text-muted-foreground">
                  {item.label}
                </div>
                <div className="truncate text-sm font-semibold tabular-nums">
                  {item.value}
                </div>
              </div>
            </div>
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          </button>
        );
      })}
    </section>
  );
}

function ProfitFlowPanel({
  revenue,
  financeConfirmedRevenue,
  financeDiffAmount,
  financeDiffPct,
  netProfit,
  ownerProfit,
  ownerMargin,
  unallocatedExpenses,
  financialFinal,
  isProvisional,
  rows,
  onOpen,
}: {
  revenue: number | null;
  financeConfirmedRevenue: number | null;
  financeDiffAmount: number | null;
  financeDiffPct: number | null;
  netProfit: number | null;
  ownerProfit: number | null;
  ownerMargin: number | null;
  unallocatedExpenses: number | null;
  financialFinal: boolean | null;
  isProvisional: boolean;
  rows: any[];
  onOpen: (d: Drilldown) => void;
}) {
  const expenseTotal = rows
    .filter((r) => r.sign === "-")
    .reduce((sum, r) => sum + positive(r.value), 0);
  const base = Math.max(positive(revenue), expenseTotal, 1);
  const resultTone: Tone =
    ownerProfit == null ? "neutral" : ownerProfit >= 0 ? "good" : "bad";
  const reconciliationTone: Tone =
    financeDiffPct == null
      ? "neutral"
      : Math.abs(financeDiffPct) > 3
        ? "bad"
        : "good";
  const finalStatus = financialFinal
    ? "финально"
    : isProvisional
      ? "предварительно"
      : "операционно";
  const controlRows = [
    {
      label: "Сверка WB",
      value: formatPercent(financeDiffPct),
      note:
        financeDiffAmount == null
          ? "нет данных"
          : `разница ${moneyCompactAbs(financeDiffAmount)}`,
      tone: reconciliationTone,
    },
    {
      label: "Неразобрано",
      value:
        positive(unallocatedExpenses) > 0
          ? moneyCompactAbs(unallocatedExpenses)
          : "нет",
      tone:
        positive(unallocatedExpenses) > 0 ? ("warn" as Tone) : ("good" as Tone),
    },
    {
      label: "Статус",
      value: finalStatus,
      note: `маржа ${formatPercent(ownerMargin)}`,
      tone: financialFinal ? ("good" as Tone) : ("warn" as Tone),
    },
  ];

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="grid items-start gap-0 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="p-4 sm:p-5">
            <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_260px] lg:items-start">
              <div>
                <h2 className="text-base font-semibold">P&L за период</h2>
                <div className="text-xs text-muted-foreground">
                  Формула по строкам, каждая сумма открывается.
                </div>
              </div>
              <div className="rounded-md border bg-background/80 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground">
                    Итог владельца
                  </span>
                  <Badge
                    variant="outline"
                    className={cn(
                      "text-[11px]",
                      financialFinal
                        ? "border-emerald-500/40 text-emerald-700"
                        : "border-amber-500/40 text-amber-700",
                    )}
                  >
                    {financialFinal
                      ? "финально"
                      : isProvisional
                        ? "предварительно"
                        : "операционно"}
                  </Badge>
                </div>
                <div
                  title={money(ownerProfit)}
                  className={cn(
                    "mt-1 text-2xl font-semibold tracking-tight tabular-nums",
                    ownerProfit != null && ownerProfit < 0
                      ? "text-rose-700"
                      : ownerProfit != null
                        ? "text-emerald-700"
                        : "text-muted-foreground",
                  )}
                >
                  {moneyCompact(ownerProfit)}
                </div>
              </div>
            </div>

            <div className="space-y-1.5">
              {rows.map((row) => {
                const Icon = row.icon;
                const value = row.value ?? null;
                const pct = Math.min(100, (positive(value) / base) * 100);
                return (
                  <button
                    key={row.key}
                    type="button"
                    onClick={() => onOpen(row.detail)}
                    className="group grid w-full grid-cols-[minmax(120px,210px)_minmax(90px,1fr)_auto] items-center gap-3 rounded-md px-2 py-1.5 text-left transition hover:bg-accent/45"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <span
                        className={cn(
                          "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                          toneSoft(row.tone),
                        )}
                      >
                        <Icon className="h-3.5 w-3.5" />
                      </span>
                      <span className="truncate text-sm font-medium">
                        {row.label}
                      </span>
                    </div>
                    <div className="min-w-[80px]">
                      <div className="h-2 overflow-hidden rounded-full bg-muted">
                        <div
                          className={cn(
                            "h-full rounded-full",
                            row.sign === "+"
                              ? "bg-emerald-500"
                              : row.tone === "warn"
                                ? "bg-amber-500"
                                : "bg-rose-500",
                          )}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                    <div
                      className={cn(
                        "flex items-center gap-1 text-right text-sm font-semibold tabular-nums",
                        row.sign === "-" && value != null
                          ? "text-rose-600"
                          : row.sign === "+" && value != null
                            ? "text-emerald-700"
                            : "",
                      )}
                    >
                      <span>
                        {value == null
                          ? "—"
                          : signedMoneyCompact(value, row.sign)}
                      </span>
                      <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 transition group-hover:opacity-100" />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div
            className={cn(
              "border-t p-4 sm:p-5 xl:border-l xl:border-t-0",
              tonePanel(resultTone),
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">Итог и контроль</h3>
                <div className="text-xs text-muted-foreground">
                  Точные суммы открываются в деталях.
                </div>
              </div>
              <button
                type="button"
                onClick={() =>
                  onOpen({
                    title: "Итог владельца",
                    value: ownerProfit,
                    subtitle: "после рекламы и нераспределенных расходов",
                    formula:
                      "Выручка - WB расходы - себестоимость - реклама - прочее + доплаты.",
                    rows: [
                      {
                        label: "Операционная выручка",
                        value: revenue,
                        op: "+",
                      },
                      {
                        label: "Расходы всего",
                        value: expenseTotal,
                        op: "-",
                      },
                      { label: "Чистая прибыль", value: netProfit, op: "info" },
                      { label: "Итог владельца", value: ownerProfit, op: "=" },
                      {
                        label: "Маржа владельца",
                        value:
                          ownerMargin == null
                            ? null
                            : formatPercent(ownerMargin),
                        op: "info",
                      },
                    ],
                  })
                }
                className="inline-flex shrink-0 items-center gap-1 rounded-md border bg-background px-2 py-1 text-xs font-medium hover:bg-accent"
              >
                Детали <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>

            <div
              className={cn(
                "mt-3 text-3xl font-semibold tracking-tight tabular-nums",
                ownerProfit != null && ownerProfit < 0
                  ? "text-rose-700"
                  : ownerProfit != null
                    ? "text-emerald-700"
                    : "text-muted-foreground",
              )}
              title={money(ownerProfit)}
            >
              {moneyCompact(ownerProfit)}
            </div>

            <div className="mt-3 grid gap-2">
              {controlRows.map((item) => (
                <AccountingMetric
                  key={item.label}
                  label={item.label}
                  value={item.value}
                  note={item.note}
                  tone={item.tone}
                />
              ))}
            </div>

            <div className="mt-3 rounded-md border bg-background/70 px-3 py-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Формула:</span>{" "}
              выручка - расходы. Полная расшифровка в строках P&L.
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function AccountingMetric({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string | null;
  tone: Tone;
}) {
  return (
    <div className="rounded-md border bg-background/75 px-2.5 py-2">
      <div className="truncate text-[11px] text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-0.5 truncate text-sm font-semibold tabular-nums",
          tone === "bad"
            ? "text-rose-700"
            : tone === "warn"
              ? "text-amber-700"
              : tone === "good"
                ? "text-emerald-700"
                : "text-foreground",
        )}
      >
        {value}
      </div>
      {note && note !== "—" ? (
        <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
          {note}
        </div>
      ) : null}
    </div>
  );
}

function MoneyLocationsPanel({
  locations,
  total,
  onOpen,
}: {
  locations: any[];
  total: number;
  onOpen: (d: Drilldown) => void;
}) {
  const main = locations.filter((x) =>
    ["wb_cash", "stock", "transit", "overstock", "for_pay"].includes(x.key),
  );

  return (
    <Card>
      <CardContent className="p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Где лежит 1 рубль</h2>
            <div className="text-xs text-muted-foreground">
              Позиции денег сейчас.
            </div>
          </div>
          <Badge variant="outline" className="text-[11px]" title={money(total)}>
            Всего {moneyCompact(total)}
          </Badge>
        </div>

        <div className="space-y-1.5">
          {main.map((item) => {
            const Icon = item.icon;
            const share = total
              ? Math.min(100, (positive(item.value) / total) * 100)
              : 0;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => onOpen(item.detail)}
                className="w-full rounded-md border bg-background/70 px-3 py-2.5 text-left transition hover:bg-accent/45"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className={cn(
                        "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                        toneSoft(item.tone),
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" />
                    </span>
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">
                        {item.label}
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        {share
                          ? `${share.toFixed(0)}% от видимой суммы`
                          : "нет суммы"}
                      </div>
                    </div>
                  </div>
                  <div
                    className="flex items-center gap-1 text-sm font-semibold tabular-nums"
                    title={money(item.value)}
                  >
                    {moneyCompact(item.value)}
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </div>
                <Progress value={share} className="mt-2 h-1" />
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function WbControlPanel({
  summary,
  onOpen,
}: {
  summary: any;
  onOpen: (d: Drilldown) => void;
}) {
  const wbExpenses = pickNum(summary, "total_wb_expenses");
  const logistics = pickNum(summary, "logistics_total");
  const logisticsShare = pickNum(summary, "logistics_share_percent");
  const netAfterExpenses = pickNum(summary, "net_profit_after_all_expenses");
  const highLogistics = (logisticsShare ?? 0) >= 70;

  return (
    <Card
      className={cn("overflow-hidden", highLogistics && "border-amber-500/45")}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold">Контроль WB</h2>
            <div className="text-xs text-muted-foreground">
              Расходы и логистика.
            </div>
          </div>
          <Badge
            variant="outline"
            className={cn(
              "shrink-0 text-[11px]",
              highLogistics
                ? "border-amber-500/40 text-amber-700"
                : "border-emerald-500/40 text-emerald-700",
            )}
          >
            {highLogistics ? "проверить" : "норма"}
          </Badge>
        </div>

        <button
          type="button"
          onClick={() =>
            onOpen({
              title: "Контроль WB расходов",
              value: wbExpenses,
              subtitle: "точные суммы по WB расходам",
              formula:
                "WB расходы включают комиссии, логистику, хранение, удержания и другие статьи.",
              rows: [
                { label: "WB расходы", value: wbExpenses, op: "-" },
                {
                  label: "Логистика",
                  value: logistics,
                  op: "-",
                  tone: highLogistics ? "warn" : "neutral",
                },
                {
                  label: "Доля логистики",
                  value:
                    logisticsShare == null
                      ? null
                      : formatPercent(logisticsShare),
                  op: "info",
                  tone: highLogistics ? "warn" : "neutral",
                },
                {
                  label: "Итог после расходов",
                  value: netAfterExpenses,
                  op: "info",
                  tone:
                    netAfterExpenses == null
                      ? "neutral"
                      : netAfterExpenses < 0
                        ? "bad"
                        : "good",
                },
              ],
              cta: { label: "Открыть расходы", to: "/expenses" },
            })
          }
          className="mt-3 w-full rounded-md border bg-background/70 px-3 py-3 text-left transition hover:bg-accent/45"
        >
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs text-muted-foreground">WB расходы</div>
              <div className="mt-0.5 text-xl font-semibold tabular-nums">
                {moneyCompact(wbExpenses)}
              </div>
            </div>
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge variant="outline" className="text-[11px]">
              логистика {formatPercent(logisticsShare)}
            </Badge>
            <Badge variant="outline" className="text-[11px]">
              итог {moneyCompact(netAfterExpenses)}
            </Badge>
          </div>
        </button>

        <Button asChild variant="outline" size="sm" className="mt-3 w-full">
          <Link to="/expenses">
            Открыть расходы <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function ExpensesWorkspace({
  groups,
  items,
  summary,
  isLoading,
  onOpen,
  dateFrom,
  dateTo,
}: {
  groups: any[];
  items: any[];
  summary: any;
  isLoading: boolean;
  onOpen: (d: Drilldown) => void;
  dateFrom: string;
  dateTo: string;
}) {
  const total =
    pickNum(summary, "total_expenses", "total_wb_expenses") ??
    groups
      .filter((g) => g.sign !== "income")
      .reduce((sum, g) => sum + positive(g.amount), 0);
  const sourceRows = groups.length ? groups : groupItemsForExpenses(items);

  return (
    <section>
      <Card>
        <CardContent className="p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-semibold">Расходы по группам</h2>
              <div className="text-xs text-muted-foreground">
                Каждая строка открывает состав.
              </div>
            </div>
            <Badge variant="outline" className="text-[11px]">
              Всего {moneyCompact(total)}
            </Badge>
          </div>

          {isLoading && !sourceRows.length ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-12" />
              ))}
            </div>
          ) : !sourceRows.length ? (
            <EmptyState
              title="Расходов нет"
              hint="За период backend не вернул расходов."
            />
          ) : (
            <div className="space-y-1">
              {sourceRows.map((group) => {
                const amount = positive(group.amount);
                const share = total ? Math.min(100, (amount / total) * 100) : 0;
                const childCount = group.children?.length ?? 0;
                return (
                  <button
                    key={group.code}
                    type="button"
                    onClick={() =>
                      onOpen(expenseGroupDetail(group, dateFrom, dateTo))
                    }
                    className="grid w-full grid-cols-[minmax(140px,1fr)_120px_auto] items-center gap-3 rounded-md px-2 py-2 text-left transition hover:bg-accent/45"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">
                        {group.label}
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className={cn(
                            "h-full rounded-full",
                            group.sign === "income"
                              ? "bg-emerald-500"
                              : "bg-rose-500",
                          )}
                          style={{ width: `${share}%` }}
                        />
                      </div>
                    </div>
                    <div
                      className={cn(
                        "text-right text-sm font-semibold tabular-nums",
                        group.sign === "income"
                          ? "text-emerald-700"
                          : "text-rose-600",
                      )}
                    >
                      {group.sign === "income" ? "+" : "−"}
                      {moneyCompactAbs(amount)}
                    </div>
                    <Badge
                      variant="outline"
                      className="justify-center text-[11px]"
                    >
                      {childCount}
                    </Badge>
                  </button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function PositionsWorkspace({
  locations,
  evidenceFor,
  onOpen,
}: {
  locations: any[];
  evidenceFor: (...keys: string[]) => any;
  onOpen: (d: Drilldown) => void;
}) {
  return (
    <section className="grid gap-4 2xl:grid-cols-2">
      <Card>
        <CardContent className="p-4 sm:p-5">
          <h2 className="mb-3 text-base font-semibold">Денежные позиции</h2>
          <div className="divide-y">
            {locations.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.key}
                  type="button"
                  className="flex w-full items-center justify-between gap-3 py-3 text-left transition hover:bg-accent/35"
                  onClick={() => onOpen(item.detail)}
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="truncate text-sm font-medium">
                      {item.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-sm font-semibold tabular-nums">
                    {money(item.value)}
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4 sm:p-5">
          <h2 className="mb-3 text-base font-semibold">Источники расчета</h2>
          <div className="space-y-2">
            <SourceLine
              label="Выручка"
              source="/money/summary"
              evidence={evidenceFor("revenue")}
            />
            <SourceLine
              label="Финансы WB"
              source="/finance/reports"
              evidence={evidenceFor("finance_confirmed_revenue")}
            />
            <SourceLine
              label="Баланс"
              source="/finance/balance"
              evidence={evidenceFor("cash_on_wb", "available_for_withdraw")}
            />
            <SourceLine
              label="Остатки"
              source="/stocks"
              evidence={evidenceFor("stock_value")}
            />
            <SourceLine
              label="Расходы"
              source="/money/expenses/breakdown"
              evidence={evidenceFor("unallocated_expenses")}
            />
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

function ControlWorkspace({
  actions,
  blockers,
  financeBlockers,
  isActionsLoading,
  isBlockersLoading,
  actionsError,
  blockersError,
  actionsIsError,
  blockersIsError,
  onRetryActions,
  onRetryBlockers,
}: any) {
  const topActions = actions.slice(0, 6);
  const topBlockers = (
    financeBlockers.length ? financeBlockers : blockers
  ).slice(0, 6);

  return (
    <section className="grid gap-4 2xl:grid-cols-2">
      <Card>
        <CardContent className="p-4 sm:p-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold">Сегодня</h2>
            <Button asChild variant="ghost" size="sm">
              <Link to="/action-center">
                Все <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
          {isActionsLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : actionsIsError ? (
            <ApiErrorState
              error={actionsError}
              endpoint="/money/actions/today"
              onRetry={onRetryActions}
            />
          ) : !topActions.length ? (
            <EmptyState
              title="Срочных задач нет"
              hint="Критичных действий на сегодня нет."
              onRetry={onRetryActions}
              retryLabel="Обновить"
            />
          ) : (
            <div className="space-y-2">
              {topActions.map((action: any, idx: number) => (
                <ActionRow key={action.id ?? idx} action={action} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4 sm:p-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold">Блокеры денег</h2>
            <Button asChild variant="ghost" size="sm">
              <Link to="/data-fix">
                Исправить <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
          {isBlockersLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : blockersIsError ? (
            <ApiErrorState
              error={blockersError}
              endpoint="/money/data-blockers"
              onRetry={onRetryBlockers}
            />
          ) : !topBlockers.length ? (
            <EmptyState
              title="Блокеров нет"
              hint="Ключевые деньги считаются без блокера."
              onRetry={onRetryBlockers}
              retryLabel="Обновить"
            />
          ) : (
            <div className="space-y-2">
              {topBlockers.map((b: any, idx: number) => (
                <BlockerRow key={`${b.code ?? "blocker"}-${idx}`} blocker={b} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function ArticlesWorkspace({
  articles,
  isLoading,
  financeDiffAmount,
  financeDiffPct,
  financeStatus,
}: {
  articles: any[];
  isLoading: boolean;
  financeDiffAmount: number | null;
  financeDiffPct: number | null;
  financeStatus: string | null;
}) {
  const profitable = topBy(articles, articleProfitAfterAds, 5, "desc");
  const loss = topBy(articles, articleProfitAfterAds, 5, "asc").filter(
    (x) => (articleProfitAfterAds(x) ?? 0) < 0,
  );
  const overstock = topBy(
    articles,
    (it) => it?.stock?.overstock_value ?? it?.stock?.stock_value,
    5,
    "desc",
  );

  return (
    <section className="grid gap-4 2xl:grid-cols-3">
      <ArticleList
        title="Прибыль"
        items={profitable}
        valueKind="profit"
        isLoading={isLoading}
      />
      <ArticleList
        title="Минус"
        items={loss}
        valueKind="profit"
        isLoading={isLoading}
      />
      <ArticleList
        title="Склад"
        items={overstock}
        valueKind="stock"
        isLoading={isLoading}
      />
      {!articles.length &&
      financeDiffAmount != null &&
      Math.abs(financeDiffAmount) > 0 ? (
        <Card className="xl:col-span-3 border-amber-500/40">
          <CardContent className="flex items-start gap-3 p-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <div className="min-w-0">
              <div className="text-sm font-medium">
                Есть расхождение между финансами WB и операционными данными
              </div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs">
                <Badge variant="outline">
                  Сумма {money(Math.abs(financeDiffAmount))}
                </Badge>
                {financeDiffPct != null ? (
                  <Badge variant="outline">
                    {formatPercent(financeDiffPct)}
                  </Badge>
                ) : null}
                {financeStatus ? (
                  <Badge variant="outline">
                    {humanizeDetailText(financeStatus)}
                  </Badge>
                ) : null}
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </section>
  );
}

function ArticleList({
  title,
  items,
  valueKind,
  isLoading,
}: {
  title: string;
  items: any[];
  valueKind: "profit" | "stock";
  isLoading: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-4 sm:p-5">
        <h2 className="mb-3 text-base font-semibold">{title}</h2>
        {isLoading && !items.length ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : !items.length ? (
          <EmptyState title="Нет данных" hint="В этом срезе карточек нет." />
        ) : (
          <div className="space-y-1">
            {items.map((item: any, idx: number) => {
              const nm = item.nm_id ?? item?.identity?.nm_id;
              const title =
                item.title ??
                item?.identity?.title ??
                item.vendor_code ??
                "Без названия";
              const vendor =
                item.vendor_code ?? item?.identity?.vendor_code ?? null;
              const profit = articleProfitAfterAds(item);
              const stock =
                item.stock_value ?? item?.stock?.stock_value ?? null;
              const value = valueKind === "profit" ? profit : stock;
              return (
                <Link
                  key={(nm ?? idx) as any}
                  to={(nm ? `/products/${nm}` : "/products") as any}
                  className="flex items-center justify-between gap-3 rounded-md px-2 py-2 transition hover:bg-accent/45"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{title}</div>
                    <div className="truncate text-[11px] text-muted-foreground">
                      {vendor ?? ""}
                      {nm ? ` · nm ${nm}` : ""}
                    </div>
                  </div>
                  <div
                    className={cn(
                      "shrink-0 text-right text-sm font-semibold tabular-nums",
                      valueKind === "profit" && value != null && value < 0
                        ? "text-rose-600"
                        : valueKind === "profit" && value != null
                          ? "text-emerald-700"
                          : "",
                    )}
                  >
                    {money(value)}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DetailSheet({
  detail,
  onOpenChange,
}: {
  detail: Drilldown | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sheet open={!!detail} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto p-0 sm:max-w-[520px]"
      >
        {detail ? (
          <>
            <SheetHeader className="border-b px-5 py-4 text-left">
              <SheetTitle className="pr-8">{detail.title}</SheetTitle>
              <SheetDescription className="text-sm">
                {detail.subtitle ?? "Детализация суммы"}
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-4 px-5 py-4">
              <div
                className={cn(
                  "rounded-lg border p-4",
                  tonePanel(detail.tone ?? valueTone(detail.value)),
                )}
              >
                <div className="text-xs text-muted-foreground">Сумма</div>
                <div className="mt-1 text-3xl font-semibold tracking-tight tabular-nums">
                  {displayDetailValue(detail.value)}
                </div>
                {detail.formula ? (
                  <div className="mt-3 text-sm text-muted-foreground">
                    {detail.formula}
                  </div>
                ) : null}
              </div>

              {detail.rows?.length ? (
                <div className="rounded-lg border bg-background">
                  {detail.rows.map((row, idx) => {
                    const note = humanizeDetailNote(row.note);
                    const body = (
                      <div
                        className={cn(
                          "flex items-center justify-between gap-3 px-3 py-3 text-sm hover:bg-accent/35",
                          idx > 0 && "border-t",
                        )}
                      >
                        <div className="min-w-0">
                          <div className="truncate font-medium">
                            {row.label}
                          </div>
                          {note ? (
                            <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
                              {note}
                            </div>
                          ) : null}
                        </div>
                        <div
                          className={cn(
                            "shrink-0 text-right font-medium tabular-nums",
                            opTone(row.op, row.tone),
                          )}
                        >
                          {formatRowValue(row)}
                        </div>
                      </div>
                    );
                    return row.href ? (
                      <Link key={idx} to={row.href as any}>
                        {body}
                      </Link>
                    ) : (
                      <div key={idx}>{body}</div>
                    );
                  })}
                </div>
              ) : null}

              {detail.cta ? (
                <Button asChild className="w-full">
                  <Link to={detail.cta.to as any}>
                    {detail.cta.label} <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
              ) : null}
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function ActionRow({ action }: { action: any }) {
  const title = action.title || action.action_type || "Действие";
  const amount = action.expected_effect_amount ?? action.required_cash ?? null;
  const linked = action.linked_entity?.nm_id ?? action.linked_sku_id ?? null;
  const trust = moneyTrustFrom(
    action.money_trust,
    action.evidence_ledger?.money_trust,
    action.payload?.money_trust,
  );

  return (
    <div className="rounded-md border bg-background/70 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{title}</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {amount != null ? (
              <Badge variant="outline" className="text-[11px]">
                эффект {money(amount)}
              </Badge>
            ) : null}
            {linked ? (
              <Badge variant="outline" className="text-[11px]">
                nm {linked}
              </Badge>
            ) : null}
            {trust?.display_label ? (
              <Badge variant="outline" className="text-[11px]">
                {trust.display_label}
              </Badge>
            ) : null}
          </div>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link to="/action-center">Открыть</Link>
        </Button>
      </div>
    </div>
  );
}

function BlockerRow({ blocker }: { blocker: any }) {
  const amount = blocker.affected_amount ?? blocker.affected_revenue ?? null;
  const problemId = blocker.problem_instance_id ?? null;
  const href = problemId
    ? `/data-fix?problem_instance_id=${encodeURIComponent(String(problemId))}`
    : "/data-fix";

  return (
    <div className="rounded-md border bg-background/70 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">
            {blocker.title || blocker.code || "Проблема"}
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {amount != null ? (
              <Badge variant="outline" className="text-[11px]">
                затронуто {money(amount)}
              </Badge>
            ) : null}
            {blocker.priority ? (
              <Badge variant="outline" className="text-[11px]">
                {String(blocker.priority)}
              </Badge>
            ) : null}
          </div>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link to={href as any}>Исправить</Link>
        </Button>
      </div>
    </div>
  );
}

function SourceLine({
  label,
  source,
  evidence,
}: {
  label: string;
  source: string;
  evidence?: any;
}) {
  const sourceLabel = humanizeMoneySource(source) ?? "Источник данных";
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border bg-background/70 px-3 py-2">
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{label}</div>
        <div className="truncate text-[11px] text-muted-foreground">
          {sourceLabel}
        </div>
      </div>
      <Badge
        variant="outline"
        className={cn(
          "text-[11px]",
          evidence
            ? "border-emerald-500/40 text-emerald-700"
            : "text-muted-foreground",
        )}
      >
        {evidence ? "есть" : "—"}
      </Badge>
    </div>
  );
}

function SideMetric({
  label,
  value,
  raw,
  tone = "neutral",
}: {
  label: string;
  value: any;
  raw?: boolean;
  tone?: Tone;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border bg-background/70 px-3 py-2">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span
        className={cn(
          "text-sm font-semibold tabular-nums",
          tone === "bad"
            ? "text-rose-700"
            : tone === "warn"
              ? "text-amber-700"
              : tone === "good"
                ? "text-emerald-700"
                : "",
        )}
      >
        {raw ? value : money(value)}
      </span>
    </div>
  );
}

function MoneyPageSkeleton() {
  return (
    <div className="w-full px-4 py-4 sm:px-5 space-y-4">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-14" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_400px] 2xl:grid-cols-[minmax(0,1fr)_420px]">
        <Skeleton className="h-[360px]" />
        <Skeleton className="h-[360px]" />
      </div>
      <Skeleton className="h-[420px]" />
    </div>
  );
}

function normalizeActions(data: any): any[] {
  const items: any[] = Array.isArray(data?.owner_focus_actions)
    ? data.owner_focus_actions
    : Array.isArray(data)
      ? data
      : Array.isArray(data?.items)
        ? data.items
        : Array.isArray(data?.actions)
          ? data.actions
          : [];
  return items
    .filter((item) => !isSystemHandledAction(item))
    .filter((item) =>
      isSellerVisibleMoneyTrust(
        item?.money_trust,
        item?.evidence_ledger?.money_trust,
        item?.payload?.money_trust,
      ),
    )
    .sort((a, b) => (b?.priority_score ?? 0) - (a?.priority_score ?? 0));
}

function normalizeBlockers(data: any): any[] {
  return [
    ...(Array.isArray(data?.blockers) ? data.blockers : []),
    ...(Array.isArray(data?.warnings) ? data.warnings : []),
    ...(Array.isArray(data?.items) ? data.items : []),
    ...(Array.isArray(data) ? data : []),
  ].filter(Boolean);
}

function normalizeArticles(data: any): any[] {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.items)) return data.items;
  return [];
}

function normalizeExpenseItems(raw: any): any[] {
  const items = Array.isArray(raw?.items) ? raw.items : [];
  return items
    .filter((item: any) => item && item.amount != null)
    .map((item: any) => ({
      ...item,
      code: item.category ?? item.code ?? item.group_key ?? "other",
      label:
        item.label ||
        item.category_label ||
        EXPENSE_CATEGORY_LABELS[item.category] ||
        categoryLabel(item.category) ||
        "Расход",
      amount: Number(item.amount),
      share_percent:
        typeof item.share_percent === "number" ? item.share_percent : null,
    }));
}

function normalizeCascadeGroups(raw: any, fallbackItems: any[]): any[] {
  const body = raw?.cascade ?? raw ?? null;
  const groups = Array.isArray(body?.groups) ? body.groups : [];
  if (groups.length) {
    return groups.map((g: any) => ({
      code: g.code ?? g.label,
      label: g.label ?? g.code ?? "Группа",
      amount: Number(g.amount ?? 0),
      sign: g.sign === "income" ? "income" : "expense",
      children: Array.isArray(g.children)
        ? g.children.map((c: any) => ({
            code: c.code ?? c.category ?? c.label,
            label: c.label ?? categoryLabel(c.code ?? c.category),
            amount: Number(c.amount ?? 0),
            source: c.source ?? null,
            share_percent: c.share_percent ?? null,
          }))
        : [],
    }));
  }
  return groupItemsForExpenses(fallbackItems);
}

function groupItemsForExpenses(items: any[]): any[] {
  if (!items.length) return [];
  const buckets = new Map<string, any>();
  for (const item of items) {
    const code = parentExpenseCode(item.code);
    const current = buckets.get(code) ?? {
      code,
      label: parentExpenseLabel(code),
      sign: isIncomeCategory(item.code) ? "income" : "expense",
      amount: 0,
      children: [],
    };
    current.amount += Number(item.amount ?? 0);
    current.children.push(item);
    buckets.set(code, current);
  }
  return Array.from(buckets.values()).sort(
    (a, b) => Math.abs(b.amount) - Math.abs(a.amount),
  );
}

function parentExpenseCode(code: string): string {
  if (["seller_cogs"].includes(code)) return "seller_cogs";
  if (["seller_other_expense", "seller_other_expenses"].includes(code))
    return "seller_other";
  if (["marketing_deduction", "ad_spend", "ads"].includes(code)) return "ads";
  if (
    [
      "compensation",
      "surcharge",
      "additional_payment",
      "additional_income",
    ].includes(code)
  )
    return "additional_income";
  return "wb_expenses";
}

function parentExpenseLabel(code: string): string {
  switch (code) {
    case "seller_cogs":
      return "Себестоимость";
    case "seller_other":
      return "Прочие расходы продавца";
    case "ads":
      return "Реклама";
    case "additional_income":
      return "Доплаты";
    default:
      return "Расходы WB";
  }
}

function isIncomeCategory(code: string): boolean {
  return [
    "compensation",
    "surcharge",
    "additional_payment",
    "additional_income",
  ].includes(code);
}

function expenseDetailFromGroup(
  title: string,
  value: number | null,
  groups: any[],
  items: any[],
  codes: string[],
  to?: string,
): Drilldown {
  const matchingGroups = groups.filter(
    (g) => codes.includes(g.code) || String(g.code).includes("wb"),
  );
  const rows = matchingGroups
    .flatMap((g) => (g.children?.length ? g.children : [g]))
    .map((it: any) => ({
      label: it.label ?? categoryLabel(it.code),
      value: Math.abs(Number(it.amount ?? 0)),
      op: it.sign === "income" ? "+" : "-",
      note: humanizeMoneySource(it.source),
      href: it.code ? reportRowsHref(it.code) : null,
    }));
  const fallbackRows = rows.length
    ? rows
    : items
        .filter(
          (it) =>
            ![
              "seller_cogs",
              "seller_other_expense",
              "marketing_deduction",
            ].includes(it.code),
        )
        .map((it) => ({
          label: it.label,
          value: Math.abs(Number(it.amount ?? 0)),
          op: "-",
          note: humanizeMoneySource(it.source),
          href: reportRowsHref(it.code),
        }));

  return {
    title,
    value,
    formula: "Комиссии, логистика, хранение, удержания и другие WB-статьи.",
    rows: fallbackRows,
    sources: ["/money/expenses/breakdown", "/money/profit-cascade"],
    cta: to ? { label: "Открыть расходы", to } : null,
  };
}

function expenseGroupDetail(
  group: any,
  dateFrom: string,
  dateTo: string,
): Drilldown {
  const rows = (group.children?.length ? group.children : [group]).map(
    (it: any) => ({
      label: it.label || categoryLabel(it.code),
      value: Math.abs(Number(it.amount ?? 0)),
      op: group.sign === "income" || it.sign === "income" ? "+" : "-",
      note:
        [
          it.share_percent != null ? formatPercent(it.share_percent) : null,
          humanizeMoneySource(it.source),
        ]
          .filter(Boolean)
          .join(" · ") || null,
      href: it.code ? reportRowsHref(it.code, dateFrom, dateTo) : null,
    }),
  );
  return {
    title: group.label,
    value: Math.abs(Number(group.amount ?? 0)),
    tone: group.sign === "income" ? "good" : "bad",
    formula:
      group.sign === "income"
        ? "Положительные корректировки."
        : "Сумма дочерних расходных статей.",
    rows,
    sources: ["/money/expenses/breakdown", "/money/profit-cascade"],
    cta: { label: "Открыть расходы", to: "/expenses" },
  };
}

function reportRowsHref(category: string, from?: string, to?: string) {
  const q = new URLSearchParams();
  q.set("category", category);
  if (from) q.set("date_from", from);
  if (to) q.set("date_to", to);
  return `/expenses?${q.toString()}`;
}

function isSystemHandledAction(action: any): boolean {
  const type = String(action?.action_type ?? "").toUpperCase();
  const category = String(action?.category ?? "").toLowerCase();
  return (
    type === "RECONCILE_FINANCE" ||
    type === "RECONCILIATION_REVIEW" ||
    category === "finance_reconcile"
  );
}

function topBy<T>(
  arr: T[],
  get: (it: T) => number | null | undefined,
  n: number,
  dir: "asc" | "desc",
): T[] {
  return arr
    .map((it) => ({ it, v: get(it) }))
    .filter(
      (x) =>
        typeof x.v === "number" && !Number.isNaN(x.v) && (x.v as number) !== 0,
    )
    .sort((a, b) =>
      dir === "desc"
        ? (b.v as number) - (a.v as number)
        : (a.v as number) - (b.v as number),
    )
    .slice(0, n)
    .map((x) => x.it);
}

function articleProfitAfterAds(item: any): number | null {
  return (
    pickNum(item, "net_profit", "net_profit_after_ads") ??
    pickNum(
      item?.money?.profit,
      "after_ads",
      "after_source_ads",
      "net_profit_after_ads",
      "net_profit",
    ) ??
    null
  );
}

function humanizeMoneySource(value: string | null | undefined): string | null {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  if (MONEY_PATH_LABELS[raw]) return MONEY_PATH_LABELS[raw];
  if (MONEY_SOURCE_LABELS[raw]) return MONEY_SOURCE_LABELS[raw];
  const normalized = raw.replace(/^\/+/, "").replace(/[/-]+/g, "_");
  if (MONEY_SOURCE_LABELS[normalized]) return MONEY_SOURCE_LABELS[normalized];
  if (/^\/?[a-z0-9_/-]+$/i.test(raw) && /[_/-]/.test(raw)) {
    return raw
      .replace(/^\/+/, "")
      .split(/[\/_-]+/)
      .filter(Boolean)
      .map((part) => {
        if (part.toLowerCase() === "wb") return "WB";
        if (part.toLowerCase() === "api") return "API";
        return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
      })
      .join(" ");
  }
  return raw;
}

function humanizeDetailText(
  value: string | number | null | undefined,
): string | null {
  if (value == null || value === "") return null;
  if (typeof value === "number") return String(value);
  const raw = String(value).trim();
  if (!raw) return null;
  return MONEY_VALUE_LABELS[raw] ?? humanizeMoneySource(raw) ?? raw;
}

function humanizeDetailNote(note: string | null | undefined): string | null {
  if (!note) return null;
  return note
    .split(" · ")
    .map((part) => humanizeDetailText(part))
    .filter(Boolean)
    .join(" · ");
}

function pickNum(obj: any, ...keys: string[]): number | null {
  for (const k of keys) {
    const v = obj?.[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return null;
}

function pickStr(obj: any, ...keys: string[]): string | null {
  for (const k of keys) {
    const v = obj?.[k];
    if (typeof v === "string" && v) return v;
  }
  return null;
}

function positive(value: number | null | undefined): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return Math.abs(value);
}

function sumNullable(
  ...values: Array<number | null | undefined>
): number | null {
  const valid = values.filter(
    (value) => typeof value === "number" && Number.isFinite(value),
  );
  if (!valid.length) return null;
  return valid.reduce((sum, value) => sum + (value as number), 0);
}

function money(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return formatMoney(value);
}

function moneyAbs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return formatMoney(Math.abs(value));
}

function moneyCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return formatMoneyCompact(value);
}

function moneyCompactAbs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return formatMoneyCompact(Math.abs(value));
}

function signedMoneyCompact(
  value: number | null | undefined,
  sign?: string,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  const prefix = sign === "-" ? "−" : sign === "+" ? "+" : "";
  return `${prefix}${moneyCompactAbs(value)}`;
}

function displayDetailValue(value: number | string | null | undefined): string {
  if (typeof value === "number") return money(value);
  if (value == null || value === "") return "—";
  return humanizeDetailText(value) ?? "—";
}

function formatRowValue(row: DetailRow): string {
  if (typeof row.value === "number") {
    const prefix = row.op === "-" ? "−" : row.op === "+" ? "+" : "";
    return `${prefix}${moneyAbs(row.value)}`;
  }
  if (row.value == null || row.value === "") return "—";
  return humanizeDetailText(row.value) ?? "—";
}

function valueTone(value: number | string | null | undefined): Tone {
  if (typeof value !== "number") return "neutral";
  return value < 0 ? "bad" : value > 0 ? "good" : "neutral";
}

function opTone(op?: string, tone?: Tone) {
  if (tone === "warn") return "text-amber-700";
  if (tone === "bad") return "text-rose-700";
  if (tone === "good") return "text-emerald-700";
  if (op === "-") return "text-rose-600";
  if (op === "+") return "text-emerald-700";
  return "text-foreground";
}

function toneSoft(tone: Tone) {
  switch (tone) {
    case "good":
      return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "warn":
      return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "bad":
      return "bg-rose-500/10 text-rose-700 dark:text-rose-300";
    case "info":
      return "bg-sky-500/10 text-sky-700 dark:text-sky-300";
    default:
      return "bg-muted text-muted-foreground";
  }
}

function toneBorder(tone: Tone) {
  switch (tone) {
    case "good":
      return "border-emerald-500/30";
    case "warn":
      return "border-amber-500/35";
    case "bad":
      return "border-rose-500/35";
    case "info":
      return "border-sky-500/30";
    default:
      return "border-border";
  }
}

function tonePanel(tone: Tone) {
  switch (tone) {
    case "good":
      return "border-emerald-500/25 bg-emerald-500/5";
    case "warn":
      return "border-amber-500/30 bg-amber-500/5";
    case "bad":
      return "border-rose-500/30 bg-rose-500/5";
    case "info":
      return "border-sky-500/25 bg-sky-500/5";
    default:
      return "bg-card";
  }
}

function rangeForDays(days: number) {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - days + 1);
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  return { from: fmt(from), to: fmt(to) };
}

function isSameRange(range: { from: string; to: string }, days: number) {
  const expected = rangeForDays(days);
  return expected.from === range.from && expected.to === range.to;
}
