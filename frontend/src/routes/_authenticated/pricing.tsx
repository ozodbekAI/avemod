import {
  useMutation,
  useQuery,
  keepPreviousData,
  useQueryClient,
} from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Calculator,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Database,
  FileSearch,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Tag,
  TrendingUp,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";

import { EndpointError } from "@/components/EndpointError";
import { PageHeader, PageShell } from "@/components/PageShell";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import {
  TrustStatusBanner,
  trustInputsFromSummary,
} from "@/components/money-ui/TrustStatusBanner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useAccounts } from "@/lib/account-context";
import { routeSearchText } from "@/lib/action-center-routing";
import { useDateRange } from "@/lib/date-range-context";
import {
  formatDate,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
} from "@/lib/format";
import {
  fetchMoneySummary,
  fetchPricingSafety,
  simulatePricing,
} from "@/lib/money-endpoints";
import { normalizeTrust } from "@/lib/trust";

export const Route = createFileRoute("/_authenticated/pricing")({
  component: PricingPage,
  validateSearch: (search: Record<string, unknown>): PricingSearch => ({
    search: routeSearchText(search.search),
    nm_id: normalizeRouteNmId(search.nm_id),
  }),
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

const PAGE_SIZE = 25;

type PricingSearch = {
  search?: string;
  nm_id?: string;
};

type ViewKey = "all" | "risk" | "margin_watch" | "not_computable" | "safe";

type PromotionDetail = {
  promotion_id: number;
  name?: string | null;
  promo_type?: string | null;
  status?: string | null;
  in_action?: boolean;
  start_at?: string | null;
  end_at?: string | null;
  price?: number | null;
  currency_code?: string | null;
  plan_price?: number | null;
  discount?: number | null;
  plan_discount?: number | null;
  plan_safe_gap?: number | null;
  plan_target_gap?: number | null;
  plan_state?: string | null;
  participation_percentage?: number | null;
  in_promo_action_leftovers?: number | null;
  in_promo_action_total?: number | null;
  not_in_promo_action_leftovers?: number | null;
  not_in_promo_action_total?: number | null;
  exception_products_count?: number | null;
  advantages?: string[];
  description?: string | null;
};

type PriceRow = {
  sku_id?: number | null;
  nm_id?: number | null;
  vendor_code?: string | null;
  title?: string | null;
  current_price?: number | null;
  current_discounted_price?: number | null;
  average_sale_price?: number | null;
  reference_price?: number | null;
  break_even_price?: number | null;
  target_margin_price?: number | null;
  safe_price_gap?: number | null;
  target_margin_gap?: number | null;
  estimated_margin_at_current_price?: number | null;
  estimated_margin_percent?: number | null;
  estimated?: boolean;
  confidence?: string | null;
  action_hint?: string | null;
  price_source?: string | null;
  calculation_state?: string | null;
  not_computable_reason?: string | null;
  not_computable_reasons?: string[];
  data_state?: string | null;
  mapping_status?: string | null;
  currency_iso_code?: string | null;
  discount?: number | null;
  club_discount?: number | null;
  editable_size_price?: boolean | null;
  is_bad_turnover?: boolean | null;
  sizes_count?: number;
  min_size_price?: number | null;
  max_size_price?: number | null;
  min_discounted_price?: number | null;
  max_discounted_price?: number | null;
  min_club_discounted_price?: number | null;
  max_club_discounted_price?: number | null;
  wholesale_discount_thresholds?: Array<Record<string, unknown>>;
  quarantine?: boolean;
  quarantine_new_price?: number | null;
  quarantine_old_price?: number | null;
  quarantine_new_discount?: number | null;
  quarantine_old_discount?: number | null;
  quarantine_price_diff?: number | null;
  promotion_calendar_synced?: boolean;
  promotion_active_count?: number;
  promotion_available_count?: number;
  promotion_names?: string[];
  promotion_nearest_name?: string | null;
  promotion_nearest_starts_at?: string | null;
  promotion_min_plan_price?: number | null;
  promotion_max_plan_discount?: number | null;
  promotion_plan_safe_gap?: number | null;
  promotion_plan_target_gap?: number | null;
  promotion_plan_state?: string | null;
  promotion_details?: PromotionDetail[];
};

type PricePage = {
  total?: number;
  limit?: number;
  offset?: number;
  items?: PriceRow[];
  rows?: PriceRow[];
  summary?: {
    total_count?: number;
    computed_count?: number;
    below_break_even_count?: number;
    not_computable_count?: number;
    price_increase_review_count?: number;
    safe_count?: number;
    below_target_margin_count?: number;
    editable_size_price_count?: number;
    bad_turnover_count?: number;
    quarantine_count?: number;
    wholesale_discount_count?: number;
    promotion_calendar_synced_count?: number;
    promotion_active_count?: number;
    promotion_available_count?: number;
    promotion_plan_below_break_even_count?: number;
    promotion_plan_below_target_count?: number;
    promotion_plan_safe_count?: number;
  };
  trust_state?: string;
  business_trusted?: boolean;
  financial_final?: boolean;
  cost_trust_policy?: string | null;
  supplier_confirmed_revenue_coverage_percent?: number;
  trusted_revenue_cost_coverage_percent?: number;
  financial_final_blockers_total?: number;
  blocking_open_issues_total?: number;
};

type PriceSimulationResult = {
  expected_revenue?: number | null;
  expected_profit?: number | null;
  expected_margin_percent?: number | null;
  risk_flag?: string | null;
};

const VIEW_META: Record<
  ViewKey,
  {
    label: string;
    status?: string;
    icon: typeof Tag;
    tone: string;
    sortBy: string;
  }
> = {
  all: {
    label: "Все",
    icon: Tag,
    tone: "border-border text-muted-foreground",
    sortBy: "risk",
  },
  risk: {
    label: "Минус",
    status: "risk",
    icon: ShieldAlert,
    tone: "border-destructive/35 text-destructive bg-destructive/5",
    sortBy: "risk",
  },
  margin_watch: {
    label: "Маржа ниже цели",
    status: "margin_watch",
    icon: TrendingUp,
    tone: "border-warning/40 text-warning bg-warning/10",
    sortBy: "target_margin_gap",
  },
  not_computable: {
    label: "Нет расчёта",
    status: "not_computable",
    icon: Database,
    tone: "border-primary/35 text-primary bg-primary/5",
    sortBy: "state",
  },
  safe: {
    label: "В норме",
    status: "safe",
    icon: ShieldCheck,
    tone: "border-success/35 text-success bg-success/5",
    sortBy: "target_margin_gap",
  },
};

const PRICE_SOURCE_LABELS: Record<string, string> = {
  current_sku: "core SKU",
  wb_price_snapshot: "WB prices",
  article_price: "mart fallback",
  average_sale: "avg sale",
  missing: "нет цены",
};

const REASON_LABELS: Record<string, string> = {
  missing_cost: "нет себестоимости",
  missing_price: "нет цены",
  not_enough_units: "нет продаж",
  revenue_not_available: "нет выручки",
  formula_not_computable: "формула недоступна",
};

function normalizeRouteNmId(value: unknown): string | undefined {
  const nmId = routeSearchText(value)?.replace(/[^\d]/g, "");
  return nmId || undefined;
}

function PricingPage() {
  const routeSearch = Route.useSearch();
  const routeSearchTerm = routeSearch.search ?? routeSearch.nm_id ?? "";
  const { activeId } = useAccounts();
  const { from: dateFrom, to: dateTo } = useDateRange();
  const qc = useQueryClient();
  const [page, setPage] = useState(0);
  const [view, setView] = useState<ViewKey>("all");
  const [search, setSearch] = useState(routeSearchTerm);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [sheetItem, setSheetItem] = useState<PriceRow | null>(null);
  const debouncedSearch = useDebouncedValue(search.trim(), 250);

  useEffect(() => {
    setSearch(routeSearchTerm);
  }, [routeSearchTerm]);

  useEffect(() => {
    setPage(0);
    setSelectedKey(null);
  }, [activeId, dateFrom, dateTo, view, debouncedSearch]);

  const overviewQ = useQuery({
    queryKey: ["pricing-safety-overview", activeId, dateFrom, dateTo],
    enabled: !!activeId,
    queryFn: () =>
      fetchPricingSafety({
        accountId: activeId!,
        dateFrom,
        dateTo,
        limit: 1,
        offset: 0,
      }) as Promise<PricePage>,
    staleTime: 60 * 1000,
  });

  const listQ = useQuery({
    queryKey: [
      "pricing-safety-list",
      activeId,
      dateFrom,
      dateTo,
      page,
      view,
      debouncedSearch,
    ],
    enabled: !!activeId,
    queryFn: () =>
      fetchPricingSafety({
        accountId: activeId!,
        dateFrom,
        dateTo,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        search: debouncedSearch || undefined,
        status: VIEW_META[view].status,
        sortBy: VIEW_META[view].sortBy,
        sortDir: view === "safe" ? "desc" : "asc",
      }) as Promise<PricePage>,
    staleTime: 60 * 1000,
    placeholderData: keepPreviousData,
  });

  const moneyQ = useQuery({
    queryKey: ["money-summary-pricing", activeId, dateFrom, dateTo],
    enabled: !!activeId,
    queryFn: () =>
      fetchMoneySummary({
        accountId: activeId ?? 0,
        dateFrom,
        dateTo,
      }),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const items = useMemo(() => rowsFrom(listQ.data), [listQ.data]);
  const overview = overviewQ.data;
  const summary = overview?.summary;
  const stats = useMemo(() => normalizeStats(summary), [summary]);
  const selectedItem = useMemo(() => {
    if (!items.length) return null;
    return items.find((item) => rowKey(item) === selectedKey) ?? items[0];
  }, [items, selectedKey]);

  useEffect(() => {
    if (!selectedItem) return;
    if (selectedKey !== rowKey(selectedItem))
      setSelectedKey(rowKey(selectedItem));
  }, [selectedItem, selectedKey]);

  const trustInputs = moneyQ.data ? trustInputsFromSummary(moneyQ.data) : null;
  const normTrust = normalizeTrust(moneyQ.data);
  const isLoading = overviewQ.isLoading || listQ.isLoading;
  const isFetching = overviewQ.isFetching || listQ.isFetching;
  const targetOnly = Math.max(0, stats.belowTargetMargin - stats.belowBE);

  return (
    <PageShell>
      <PageHeader
        title="Pricing Control"
        description={`${dateFrom} - ${dateTo}`}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              qc.invalidateQueries({
                predicate: (q) => String(q.queryKey[0]).startsWith("pricing-"),
              });
              qc.invalidateQueries({ queryKey: ["money-summary-pricing"] });
            }}
            disabled={isFetching}
          >
            <RefreshCw
              className={`mr-1.5 h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
            />
            Обновить
          </Button>
        }
      />

      {activeId ? (
        <DataDependencyNotice
          accountId={activeId}
          domains={[
            "prices",
            "promotions",
            "sales",
            "orders",
            "finance",
            "product_cards",
          ]}
        />
      ) : null}

      {trustInputs ? (
        <div
          data-business-trusted={normTrust.businessTrusted}
          data-financial-final={normTrust.financialFinal}
        >
          <TrustStatusBanner
            trust={trustInputs.trust}
            quality={trustInputs.quality}
            className="mb-3"
          />
        </div>
      ) : null}

      {!activeId ? (
        <Alert>
          <AlertTitle>Не выбран кабинет</AlertTitle>
          <AlertDescription>Выберите кабинет в шапке.</AlertDescription>
        </Alert>
      ) : null}

      {isLoading ? <PricingSkeleton /> : null}

      {overviewQ.isError || listQ.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Ошибка загрузки pricing</AlertTitle>
          <AlertDescription>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                overviewQ.refetch();
                listQ.refetch();
              }}
            >
              Повторить
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {overview && !isLoading ? (
        <>
          <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricTile
              label="Ниже break-even"
              value={stats.belowBE}
              detail={stats.belowBE ? "цена ниже нуля" : "критичных нет"}
              tone={stats.belowBE ? "danger" : "success"}
              active={view === "risk"}
              icon={stats.belowBE ? ShieldAlert : ShieldCheck}
              onClick={() => setView(view === "risk" ? "all" : "risk")}
            />
            <MetricTile
              label="Маржа ниже цели"
              value={targetOnly || stats.belowTargetMargin}
              detail="сравнение с target margin"
              tone={
                targetOnly || stats.belowTargetMargin ? "warning" : "success"
              }
              active={view === "margin_watch"}
              icon={TrendingUp}
              onClick={() =>
                setView(view === "margin_watch" ? "all" : "margin_watch")
              }
            />
            <MetricTile
              label="Нет расчёта"
              value={stats.notComputable}
              detail={`${percent(stats.notComputable, stats.total)} от очереди`}
              tone={stats.notComputable ? "info" : "success"}
              active={view === "not_computable"}
              icon={Database}
              onClick={() =>
                setView(view === "not_computable" ? "all" : "not_computable")
              }
            />
            <CoverageTile
              label="Cost coverage"
              value={overview.trusted_revenue_cost_coverage_percent ?? 0}
              blockers={overview.financial_final_blockers_total ?? 0}
              final={overview.financial_final === true}
            />
          </section>

          <OperationalStrip stats={stats} />

          {stats.notComputable > 0 ? (
            <Alert className="border-warning/35 bg-warning/10">
              <AlertTriangle className="h-4 w-4 text-warning" />
              <AlertTitle>Pricing queue не полный</AlertTitle>
              <AlertDescription>
                {stats.notComputable} SKU без расчёта. Главный источник
                блокировки — себестоимость.{" "}
                <Link
                  to="/costs"
                  className="font-medium underline underline-offset-2"
                >
                  Открыть costs
                </Link>
              </AlertDescription>
            </Alert>
          ) : null}

          <section className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_430px]">
            <Card className="min-w-0 overflow-hidden">
              <CardHeader className="border-b pb-3">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
                      Очередь решений
                    </CardTitle>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {listQ.data?.total ?? 0} SKU в текущем срезе
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="relative w-full min-w-[230px] sm:w-[280px]">
                      <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="nm_id, SKU, vendor_code"
                        className="h-9 pl-8 text-xs"
                      />
                    </div>
                  </div>
                </div>
                <ViewSwitcher value={view} onChange={setView} stats={stats} />
              </CardHeader>
              <CardContent className="p-0">
                {items.length ? (
                  <div className="divide-y">
                    {items.map((item) => (
                      <QueueRow
                        key={rowKey(item)}
                        item={item}
                        active={rowKey(item) === rowKey(selectedItem)}
                        onSelect={() => setSelectedKey(rowKey(item))}
                        onOpen={() => setSheetItem(item)}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyQueue search={debouncedSearch} />
                )}
                <div className="flex items-center justify-between border-t px-3 py-2 text-xs text-muted-foreground">
                  <span>
                    Стр. {page + 1} · показано {items.length}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 px-2"
                      disabled={page === 0 || listQ.isFetching}
                      onClick={() =>
                        setPage((current) => Math.max(0, current - 1))
                      }
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 px-2"
                      disabled={items.length < PAGE_SIZE || listQ.isFetching}
                      onClick={() => setPage((current) => current + 1)}
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>

            <DecisionPanel
              item={selectedItem}
              accountId={activeId}
              dateFrom={dateFrom}
              dateTo={dateTo}
              onOpen={() => selectedItem && setSheetItem(selectedItem)}
            />
          </section>
        </>
      ) : null}

      <PriceDetailSheet
        item={sheetItem}
        accountId={activeId}
        dateFrom={dateFrom}
        dateTo={dateTo}
        onClose={() => setSheetItem(null)}
      />
    </PageShell>
  );
}

function rowsFrom(data: PricePage | PriceRow[] | undefined): PriceRow[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  return data.items ?? data.rows ?? [];
}

function normalizeStats(summary: PricePage["summary"] | undefined) {
  const n = (value: unknown) =>
    typeof value === "number" && Number.isFinite(value)
      ? value
      : Number(value) || 0;
  const computed = n(summary?.computed_count);
  const notComputable = n(summary?.not_computable_count);
  return {
    total: n(summary?.total_count) || computed + notComputable,
    computed,
    notComputable,
    belowBE: n(summary?.below_break_even_count),
    belowTargetMargin: n(summary?.below_target_margin_count),
    safe: n(summary?.safe_count),
    priceIncreaseReview: n(summary?.price_increase_review_count),
    editableSizePrice: n(summary?.editable_size_price_count),
    badTurnover: n(summary?.bad_turnover_count),
    quarantine: n(summary?.quarantine_count),
    wholesaleDiscount: n(summary?.wholesale_discount_count),
    promotionCalendarSynced: n(summary?.promotion_calendar_synced_count),
    promotionActive: n(summary?.promotion_active_count),
    promotionAvailable: n(summary?.promotion_available_count),
    promotionPlanBelowBE: n(summary?.promotion_plan_below_break_even_count),
    promotionPlanBelowTarget: n(summary?.promotion_plan_below_target_count),
    promotionPlanSafe: n(summary?.promotion_plan_safe_count),
  };
}

function rowKey(item: PriceRow | null | undefined): string {
  if (!item) return "";
  return String(item.sku_id ?? item.nm_id ?? item.vendor_code ?? "unknown");
}

function num(value: unknown): number | null {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function referencePrice(item: PriceRow | null | undefined): number | null {
  if (!item) return null;
  return (
    num(item.reference_price) ??
    num(item.current_discounted_price) ??
    num(item.current_price) ??
    num(item.average_sale_price)
  );
}

function targetGap(item: PriceRow | null | undefined): number | null {
  if (!item) return null;
  const explicit = num(item.target_margin_gap);
  if (explicit != null) return explicit;
  const ref = referencePrice(item);
  const target = num(item.target_margin_price);
  return ref != null && target != null ? ref - target : null;
}

function safetyState(
  item: PriceRow | null | undefined,
): "risk" | "target" | "safe" | "blocked" {
  if (
    !item ||
    String(item.calculation_state ?? "").toLowerCase() !== "computed"
  )
    return "blocked";
  const safeGap = num(item.safe_price_gap);
  if (safeGap != null && safeGap < 0) return "risk";
  const tGap = targetGap(item);
  if (tGap != null && tGap < 0) return "target";
  return "safe";
}

function percent(part: number, total: number): string {
  if (!total) return "0%";
  return `${Math.round((part / total) * 100)}%`;
}

function reasonText(item: PriceRow | null | undefined): string {
  const reasons = item?.not_computable_reasons?.length
    ? item.not_computable_reasons
    : item?.not_computable_reason
      ? [item.not_computable_reason]
      : [];
  return reasons.map((reason) => REASON_LABELS[reason] ?? reason).join(", ");
}

function sourceLabel(source: unknown): string {
  const key = String(source ?? "missing");
  return PRICE_SOURCE_LABELS[key] ?? key;
}

function percentValue(value: unknown): string {
  const parsed = num(value);
  return parsed == null ? "—" : `${Math.round(parsed)}%`;
}

function positivePercent(value: unknown): number | null {
  const parsed = num(value);
  return parsed != null && parsed > 0 ? parsed : null;
}

function priceRange(min: unknown, max: unknown): string {
  const lo = num(min);
  const hi = num(max);
  if (lo == null && hi == null) return "—";
  if (lo != null && hi != null && lo !== hi) {
    return `${formatMoneyCompact(lo)} - ${formatMoneyCompact(hi)}`;
  }
  return formatMoneyCompact(lo ?? hi);
}

function hasWholesale(item: PriceRow | null | undefined): boolean {
  return Boolean(item?.wholesale_discount_thresholds?.length);
}

function promotionNameDetail(item: PriceRow | null | undefined): string {
  const names = item?.promotion_names?.filter(Boolean) ?? [];
  if (names.length) return names.slice(0, 2).join(", ");
  if (item?.promotion_nearest_name) return item.promotion_nearest_name;
  if (item?.promotion_nearest_starts_at) {
    return `старт ${formatDate(item.promotion_nearest_starts_at)}`;
  }
  return "по Promotion Calendar";
}

function promotionSignalValue(item: PriceRow | null | undefined): string {
  if (!item?.promotion_calendar_synced) return "нет данных";
  if ((item.promotion_active_count ?? 0) > 0) return "участвует";
  if ((item.promotion_available_count ?? 0) > 0) return "доступна";
  return "не участвует";
}

function promotionSignalDetail(item: PriceRow | null | undefined): string {
  if (!item?.promotion_calendar_synced) {
    return "Promotion Calendar не загружен";
  }
  if ((item.promotion_active_count ?? 0) > 0) {
    return promotionNameDetail(item);
  }
  if ((item.promotion_available_count ?? 0) > 0) {
    const plan = item.promotion_min_plan_price
      ? `план ${formatMoneyCompact(item.promotion_min_plan_price)}`
      : "можно добавить";
    const discount = item.promotion_max_plan_discount
      ? `до ${percentValue(item.promotion_max_plan_discount)}`
      : null;
    return [plan, discount].filter(Boolean).join(" · ");
  }
  return "нет активной акции";
}

function promotionPlanState(item: PriceRow | null | undefined): string {
  return String(item?.promotion_plan_state ?? "")
    .trim()
    .toLowerCase();
}

function hasPromotionPlanRisk(item: PriceRow | null | undefined): boolean {
  const state = promotionPlanState(item);
  return state === "below_break_even" || state === "below_target";
}

function promotionPlanValue(item: PriceRow | null | undefined): string {
  const state = promotionPlanState(item);
  if (!item?.promotion_min_plan_price) return "нет плана";
  if (state === "below_break_even") return "ниже нуля";
  if (state === "below_target") return "ниже цели";
  if (state === "safe") return "безопасно";
  if (state === "not_computable") return "нет расчёта";
  return "план есть";
}

function promotionPlanDetail(item: PriceRow | null | undefined): string {
  if (!item?.promotion_min_plan_price) return "плановой цены нет";
  const state = promotionPlanState(item);
  const plan = `план ${formatMoneyCompact(item.promotion_min_plan_price)}`;
  if (state === "below_break_even") {
    return `${plan} · до нуля ${formatMoneyCompact(item.promotion_plan_safe_gap)}`;
  }
  if (state === "below_target") {
    return `${plan} · до цели ${formatMoneyCompact(item.promotion_plan_target_gap)}`;
  }
  if (state === "safe") {
    const gap = item.promotion_plan_target_gap ?? item.promotion_plan_safe_gap;
    return `${plan} · запас ${formatMoneyCompact(gap)}`;
  }
  return `${plan} · нужна экономика`;
}

function promotionPlanTone(
  item: PriceRow | null | undefined,
): "default" | "info" | "warning" | "danger" {
  const state = promotionPlanState(item);
  if (state === "below_break_even") return "danger";
  if (state === "below_target" || state === "not_computable") return "warning";
  if (state === "safe") return "info";
  return "default";
}

function promotionDetailPlanState(
  item: PromotionDetail | null | undefined,
): string {
  return String(item?.plan_state ?? "")
    .trim()
    .toLowerCase();
}

function promotionDetailPlanValue(
  item: PromotionDetail | null | undefined,
): string {
  const state = promotionDetailPlanState(item);
  if (!item?.plan_price) return "нет плана";
  if (state === "below_break_even") return "ниже нуля";
  if (state === "below_target") return "ниже цели";
  if (state === "safe") return "безопасно";
  if (state === "not_computable") return "нет расчёта";
  return "план есть";
}

function promotionDetailTone(
  item: PromotionDetail | null | undefined,
): "default" | "info" | "warning" | "danger" {
  const state = promotionDetailPlanState(item);
  if (state === "below_break_even") return "danger";
  if (state === "below_target" || state === "not_computable") return "warning";
  if (state === "safe") return "info";
  return "default";
}

function promotionStatusLabel(status: unknown): string {
  const key = String(status ?? "")
    .trim()
    .toLowerCase();
  if (key === "active") return "участвует";
  if (key === "scheduled") return "запланировано";
  if (key === "available") return "доступна";
  return "unknown";
}

function promotionStatusClass(status: unknown): string {
  const key = String(status ?? "")
    .trim()
    .toLowerCase();
  if (key === "active") return "border-primary/35 bg-primary/5 text-primary";
  if (key === "scheduled")
    return "border-warning/40 bg-warning/10 text-warning";
  if (key === "available") return "border-border bg-background text-foreground";
  return "border-muted-foreground/30 text-muted-foreground";
}

function promotionDateRange(item: PromotionDetail): string {
  const start = item.start_at ? formatDate(item.start_at) : "—";
  const end = item.end_at ? formatDate(item.end_at) : "—";
  return `${start} - ${end}`;
}

function promotionStatsLine(item: PromotionDetail): string {
  const parts = [
    item.promo_type ? `type ${item.promo_type}` : null,
    item.participation_percentage != null
      ? `участие ${item.participation_percentage}%`
      : null,
    item.in_promo_action_total != null
      ? `в акции ${item.in_promo_action_total}`
      : null,
    item.not_in_promo_action_total != null
      ? `доступно ${item.not_in_promo_action_total}`
      : null,
    item.exception_products_count != null
      ? `исключений ${item.exception_products_count}`
      : null,
  ].filter(Boolean);
  return parts.join(" · ") || `promotion ${item.promotion_id}`;
}

function promotionDiscountLine(item: PromotionDetail): string {
  const current = item.discount != null ? percentValue(item.discount) : "—";
  const plan =
    item.plan_discount != null ? percentValue(item.plan_discount) : "—";
  return `${current} → ${plan}`;
}

function hasWbAttention(item: PriceRow | null | undefined): boolean {
  return Boolean(
    item?.quarantine ||
    item?.is_bad_turnover ||
    item?.editable_size_price ||
    hasPromotionPlanRisk(item) ||
    (item?.promotion_active_count ?? 0) > 0 ||
    (item?.promotion_available_count ?? 0) > 0 ||
    hasWholesale(item),
  );
}

function MetricTile({
  label,
  value,
  detail,
  tone,
  active,
  icon: Icon,
  onClick,
}: {
  label: string;
  value: number;
  detail: string;
  tone: "danger" | "warning" | "info" | "success";
  active?: boolean;
  icon: typeof AlertTriangle;
  onClick?: () => void;
}) {
  const toneClass =
    tone === "danger"
      ? "border-destructive/30 bg-destructive/5 text-destructive"
      : tone === "warning"
        ? "border-warning/35 bg-warning/10 text-warning"
        : tone === "success"
          ? "border-success/30 bg-success/5 text-success"
          : "border-primary/30 bg-primary/5 text-primary";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md border p-3 text-left transition hover:bg-accent ${active ? "ring-2 ring-current ring-offset-1" : ""} ${toneClass}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-medium uppercase text-muted-foreground">
          {label}
        </span>
        <Icon className="h-4 w-4" />
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
    </button>
  );
}

function CoverageTile({
  label,
  value,
  blockers,
  final,
}: {
  label: string;
  value: number;
  blockers: number;
  final: boolean;
}) {
  const normalized = Math.max(0, Math.min(100, value || 0));
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-medium uppercase text-muted-foreground">
          {label}
        </span>
        <Badge
          variant="outline"
          className={
            final
              ? "border-success/30 text-success"
              : "border-warning/35 text-warning"
          }
        >
          {final ? "final" : "provisional"}
        </Badge>
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <div className="text-2xl font-semibold tabular-nums">
          {normalized.toFixed(1)}%
        </div>
        <div className="text-xs text-muted-foreground">{blockers} blockers</div>
      </div>
      <Progress value={normalized} className="mt-3 h-1.5" />
    </div>
  );
}

function OperationalStrip({
  stats,
}: {
  stats: ReturnType<typeof normalizeStats>;
}) {
  const promoRisk = stats.promotionPlanBelowBE + stats.promotionPlanBelowTarget;
  const items = [
    {
      label: "Цены по размерам",
      value: stats.editableSizePrice,
      detail: "индив. размеры",
      icon: SlidersHorizontal,
      tone: "text-primary",
    },
    {
      label: "Низкая оборач.",
      value: stats.badTurnover,
      detail: "флаг WB",
      icon: AlertTriangle,
      tone: stats.badTurnover ? "text-warning" : "text-muted-foreground",
    },
    {
      label: "Карантин цен",
      value: stats.quarantine,
      detail: "изменение блок.",
      icon: ShieldAlert,
      tone: stats.quarantine ? "text-destructive" : "text-muted-foreground",
    },
    {
      label: "B2B скидки",
      value: stats.wholesaleDiscount,
      detail: "оптовые уровни",
      icon: Tag,
      tone: "text-primary",
    },
    {
      label: "Акции WB",
      value: stats.promotionActive,
      detail: stats.promotionCalendarSynced
        ? `${stats.promotionAvailable} доступны`
        : "календарь не загружен",
      icon: CalendarDays,
      tone: stats.promotionActive
        ? "text-primary"
        : stats.promotionCalendarSynced
          ? "text-muted-foreground"
          : "text-warning",
    },
    {
      label: "Промо риск",
      value: promoRisk,
      detail: stats.promotionPlanBelowBE
        ? `${stats.promotionPlanBelowBE} ниже нуля`
        : stats.promotionPlanBelowTarget
          ? `${stats.promotionPlanBelowTarget} ниже цели`
          : stats.promotionPlanSafe
            ? `${stats.promotionPlanSafe} безопасно`
            : "планов нет",
      icon: Calculator,
      tone: stats.promotionPlanBelowBE
        ? "text-destructive"
        : stats.promotionPlanBelowTarget
          ? "text-warning"
          : stats.promotionPlanSafe
            ? "text-primary"
            : "text-muted-foreground",
    },
  ];
  return (
    <section className="grid gap-2 md:grid-cols-2 xl:grid-cols-6">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div
            key={item.label}
            className="flex min-h-[72px] items-center justify-between gap-3 rounded-md border bg-card px-3 py-2"
          >
            <div className="min-w-0">
              <div className="text-[11px] font-medium uppercase text-muted-foreground">
                {item.label}
              </div>
              <div className="mt-0.5 truncate text-xs text-muted-foreground">
                {item.detail}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Icon className={`h-4 w-4 ${item.tone}`} />
              <span className="text-lg font-semibold tabular-nums">
                {item.value}
              </span>
            </div>
          </div>
        );
      })}
    </section>
  );
}

function ViewSwitcher({
  value,
  onChange,
  stats,
}: {
  value: ViewKey;
  onChange: (value: ViewKey) => void;
  stats: ReturnType<typeof normalizeStats>;
}) {
  const counts: Record<ViewKey, number> = {
    all: stats.total,
    risk: stats.belowBE,
    margin_watch:
      Math.max(0, stats.belowTargetMargin - stats.belowBE) ||
      stats.belowTargetMargin,
    not_computable: stats.notComputable,
    safe: stats.safe,
  };
  return (
    <div className="flex flex-wrap gap-2 pt-1">
      {(Object.keys(VIEW_META) as ViewKey[]).map((key) => {
        const meta = VIEW_META[key];
        const Icon = meta.icon;
        return (
          <Button
            key={key}
            type="button"
            variant={value === key ? "default" : "outline"}
            size="sm"
            className="h-8 gap-1.5 text-xs"
            onClick={() => onChange(key)}
          >
            <Icon className="h-3.5 w-3.5" />
            {meta.label}
            <span className="tabular-nums opacity-75">{counts[key]}</span>
          </Button>
        );
      })}
    </div>
  );
}

function QueueRow({
  item,
  active,
  onSelect,
  onOpen,
}: {
  item: PriceRow;
  active?: boolean;
  onSelect: () => void;
  onOpen: () => void;
}) {
  const state = safetyState(item);
  const ref = referencePrice(item);
  const safeGap = num(item.safe_price_gap);
  const tGap = targetGap(item);
  const margin =
    num(item.estimated_margin_at_current_price) ??
    num(item.estimated_margin_percent);
  const discount = positivePercent(item.discount);
  const clubDiscount = positivePercent(item.club_discount);
  const computed =
    String(item.calculation_state ?? "").toLowerCase() === "computed";
  const stateMeta =
    state === "risk"
      ? {
          label: "ниже нуля",
          cls: "border-destructive/35 bg-destructive/5 text-destructive",
          icon: XCircle,
        }
      : state === "target"
        ? {
            label: "ниже цели",
            cls: "border-warning/40 bg-warning/10 text-warning",
            icon: TrendingUp,
          }
        : state === "safe"
          ? {
              label: "в норме",
              cls: "border-success/35 bg-success/5 text-success",
              icon: CheckCircle2,
            }
          : {
              label: "нет расчёта",
              cls: "border-primary/35 bg-primary/5 text-primary",
              icon: Database,
            };
  const Icon = stateMeta.icon;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      className={`grid min-w-0 w-full grid-cols-1 gap-2 border-l-2 border-l-transparent px-3 py-2 text-left transition hover:bg-accent/50 lg:grid-cols-[minmax(240px,1.35fr)_minmax(220px,0.9fr)_88px] lg:items-center ${
        active ? "border-l-primary bg-primary/5" : ""
      }`}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs font-semibold">
            {item.nm_id ?? "—"}
          </span>
          <Badge variant="outline" className={`text-[10px] ${stateMeta.cls}`}>
            <Icon className="mr-1 h-3 w-3" />
            {stateMeta.label}
          </Badge>
        </div>
        <div
          className="mt-0.5 truncate text-sm font-medium leading-5"
          title={item.title ?? item.vendor_code ?? ""}
        >
          {item.title ?? item.vendor_code ?? "Без названия"}
        </div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground">
          {item.vendor_code ?? "vendor_code не указан"}
        </div>
        <div className="mt-1 flex flex-wrap gap-1">
          {discount ? (
            <Badge variant="secondary" className="h-5 text-[9px]">
              Скидка WB {percentValue(discount)}
            </Badge>
          ) : null}
          {clubDiscount ? (
            <Badge
              variant="outline"
              className="h-5 border-primary/25 bg-primary/5 text-[9px] text-primary"
            >
              WB Club {percentValue(clubDiscount)}
            </Badge>
          ) : null}
          {(item.promotion_active_count ?? 0) > 0 ? (
            <Badge
              variant="outline"
              className="h-5 border-primary/30 bg-primary/5 text-[9px] text-primary"
            >
              Акция WB {item.promotion_active_count}
            </Badge>
          ) : null}
          {(item.promotion_active_count ?? 0) <= 0 &&
          (item.promotion_available_count ?? 0) > 0 ? (
            <Badge variant="outline" className="h-5 text-[9px]">
              Доступна акция {item.promotion_available_count}
            </Badge>
          ) : null}
          {hasPromotionPlanRisk(item) ? (
            <Badge
              variant="outline"
              className={`h-5 text-[9px] ${
                promotionPlanState(item) === "below_break_even"
                  ? "border-destructive/35 text-destructive"
                  : "border-warning/40 text-warning"
              }`}
            >
              План акции {promotionPlanValue(item)}
            </Badge>
          ) : null}
          {item.editable_size_price ? (
            <Badge variant="outline" className="h-5 text-[9px]">
              цены по размерам
            </Badge>
          ) : null}
          {item.is_bad_turnover ? (
            <Badge
              variant="outline"
              className="h-5 border-warning/35 text-[9px] text-warning"
            >
              низкая оборач.
            </Badge>
          ) : null}
          {item.quarantine ? (
            <Badge
              variant="outline"
              className="h-5 border-destructive/35 text-[9px] text-destructive"
            >
              карантин цен
            </Badge>
          ) : null}
          {hasWholesale(item) ? (
            <Badge variant="outline" className="h-5 text-[9px]">
              B2B уровни
            </Badge>
          ) : null}
        </div>
      </div>

      <div className="grid min-w-0 self-center grid-cols-3 gap-1.5 text-xs">
        <QueueMetric
          label="Цена"
          value={priceRange(
            item.min_discounted_price ?? ref,
            item.max_discounted_price ?? ref,
          )}
        />
        <QueueMetric
          label="До нуля"
          value={computed ? formatMoneyCompact(safeGap) : "—"}
          danger={(safeGap ?? 0) < 0}
        />
        <QueueMetric
          label="До цели"
          value={computed ? formatMoneyCompact(tGap) : "—"}
          danger={(tGap ?? 0) < 0}
        />
      </div>

      <div className="flex items-center justify-between gap-1.5 self-center lg:justify-end">
        <div className="text-right">
          <div
            className={`text-sm font-semibold tabular-nums ${margin != null && margin < 0 ? "text-destructive" : ""}`}
          >
            {formatPercent(margin)}
          </div>
          <div className="text-[10px] text-muted-foreground">
            {sourceLabel(item.price_source)}
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-8 px-2"
          onClick={(event) => {
            event.stopPropagation();
            onOpen();
          }}
        >
          <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function QueueMetric({
  label,
  value,
  danger,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="min-w-0 rounded-sm px-1 py-0.5">
      <div className="text-[9px] uppercase leading-3 text-muted-foreground">
        {label}
      </div>
      <div
        className={`truncate text-xs font-semibold leading-4 tabular-nums ${danger ? "text-destructive" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}

function DecisionPanel({
  item,
  accountId,
  dateFrom,
  dateTo,
  onOpen,
}: {
  item: PriceRow | null;
  accountId: number | null;
  dateFrom: string;
  dateTo: string;
  onOpen: () => void;
}) {
  if (!item) {
    return (
      <Card className="min-h-[360px]">
        <CardContent className="flex h-full min-h-[360px] items-center justify-center">
          <div className="text-center text-sm text-muted-foreground">
            <FileSearch className="mx-auto mb-2 h-8 w-8" />
            SKU не выбран
          </div>
        </CardContent>
      </Card>
    );
  }
  const state = safetyState(item);
  const ref = referencePrice(item);
  const safeGap = num(item.safe_price_gap);
  const tGap = targetGap(item);
  const breakEven = num(item.break_even_price);
  const target = num(item.target_margin_price);
  const margin =
    num(item.estimated_margin_at_current_price) ??
    num(item.estimated_margin_percent);
  const chartData = [
    { name: "Цена", value: ref ?? 0 },
    { name: "Break-even", value: breakEven ?? 0 },
    { name: "Target", value: target ?? 0 },
  ];
  return (
    <Card className="min-w-0 h-fit xl:sticky xl:top-4">
      <CardHeader className="border-b pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="truncate text-base">
              {item.title ?? item.vendor_code ?? item.nm_id}
            </CardTitle>
            <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
              <span className="font-mono">{item.nm_id}</span>
              <span>{item.vendor_code}</span>
            </div>
          </div>
          <StateBadge state={state} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <div className="grid gap-2 sm:grid-cols-2">
          <PanelValue label="Эффективная цена" value={formatMoney(ref)} />
          <PanelValue
            label="Маржа сейчас"
            value={formatPercent(margin)}
            tone={margin != null && margin < 0 ? "danger" : undefined}
          />
          <PanelValue
            label="Запас до нуля"
            value={formatMoney(safeGap)}
            tone={safeGap != null && safeGap < 0 ? "danger" : "success"}
          />
          <PanelValue
            label="Запас до цели"
            value={formatMoney(tGap)}
            tone={tGap != null && tGap < 0 ? "warning" : "success"}
          />
        </div>

        <WbSignalGrid item={item} />

        <div className="h-[180px] rounded-md border bg-muted/20 p-2">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              margin={{ top: 12, right: 8, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="name"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11 }}
              />
              <YAxis hide domain={[0, "dataMax + 1000"]} />
              <RechartsTooltip
                formatter={(value) => formatMoney(Number(value))}
              />
              <ReferenceLine y={0} stroke="var(--border)" />
              <Bar
                dataKey="value"
                fill="var(--primary)"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {state === "blocked" ? (
          <Alert className="border-warning/35 bg-warning/10">
            <Database className="h-4 w-4 text-warning" />
            <AlertTitle>Нет полной экономики</AlertTitle>
            <AlertDescription>
              {reasonText(item) || "Расчёт заблокирован источниками данных."}
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={onOpen}>
            <BarChart3 className="mr-1.5 h-4 w-4" />
            Детали
          </Button>
          {item.nm_id ? (
            <Button asChild size="sm" variant="outline">
              <Link to="/products/$nmId" params={{ nmId: String(item.nm_id) }}>
                <ArrowRight className="mr-1.5 h-4 w-4" />
                Product 360
              </Link>
            </Button>
          ) : null}
        </div>

        <SimulationInline
          item={item}
          accountId={accountId}
          dateFrom={dateFrom}
          dateTo={dateTo}
          compact
        />
      </CardContent>
    </Card>
  );
}

function PanelValue({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "danger" | "warning" | "success";
}) {
  const cls =
    tone === "danger"
      ? "text-destructive"
      : tone === "warning"
        ? "text-warning"
        : tone === "success"
          ? "text-success"
          : "";
  return (
    <div className="min-w-0 rounded-md border border-border/70 bg-muted/20 px-3 py-2.5 shadow-sm">
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div
        className={`mt-1 truncate text-sm font-semibold tabular-nums ${cls}`}
      >
        {value}
      </div>
    </div>
  );
}

function DetailSummaryRail({ item }: { item: PriceRow }) {
  const ref = referencePrice(item);
  const safeGap = num(item.safe_price_gap);
  const tGap = targetGap(item);
  const margin =
    num(item.estimated_margin_at_current_price) ??
    num(item.estimated_margin_percent);
  const gapTone =
    safeGap != null && safeGap < 0
      ? "danger"
      : tGap != null && tGap < 0
        ? "warning"
        : safeGap != null || tGap != null
          ? "success"
          : "default";
  return (
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      <DetailStat
        icon={Tag}
        label="Эффективная цена"
        value={formatMoneyCompact(ref)}
        detail={sourceLabel(item.price_source)}
      />
      <DetailStat
        icon={TrendingUp}
        label="Маржа сейчас"
        value={formatPercent(margin)}
        detail={item.confidence ?? item.calculation_state ?? "unknown"}
        tone={margin != null && margin < 0 ? "danger" : "default"}
      />
      <DetailStat
        icon={CalendarDays}
        label="План WB акции"
        value={
          item.promotion_min_plan_price
            ? formatMoneyCompact(item.promotion_min_plan_price)
            : "нет"
        }
        detail={promotionPlanValue(item)}
        tone={promotionPlanTone(item)}
      />
      <DetailStat
        icon={ShieldCheck}
        label="Запас до цели"
        value={formatMoneyCompact(tGap ?? safeGap)}
        detail={
          safeGap != null
            ? `до нуля ${formatMoneyCompact(safeGap)}`
            : "экономика неполная"
        }
        tone={gapTone}
      />
    </div>
  );
}

function DetailStat({
  icon: Icon,
  label,
  value,
  detail,
  tone = "default",
}: {
  icon: typeof Tag;
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "info" | "warning" | "danger" | "success";
}) {
  const wrapCls =
    tone === "danger"
      ? "border-destructive/30 bg-destructive/5"
      : tone === "warning"
        ? "border-warning/35 bg-warning/10"
        : tone === "info"
          ? "border-primary/30 bg-primary/5"
          : tone === "success"
            ? "border-success/30 bg-success/5"
            : "border-border/80 bg-background";
  const iconCls =
    tone === "danger"
      ? "bg-destructive/10 text-destructive"
      : tone === "warning"
        ? "bg-warning/15 text-warning"
        : tone === "info"
          ? "bg-primary/10 text-primary"
          : tone === "success"
            ? "bg-success/10 text-success"
            : "bg-muted text-muted-foreground";
  const valueCls =
    tone === "danger"
      ? "text-destructive"
      : tone === "warning"
        ? "text-warning"
        : tone === "info"
          ? "text-primary"
          : tone === "success"
            ? "text-success"
            : "text-foreground";
  return (
    <div className={`min-w-0 rounded-md border px-3 py-2 shadow-sm ${wrapCls}`}>
      <div className="flex min-w-0 items-center gap-2">
        <span
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${iconCls}`}
        >
          <Icon className="h-3.5 w-3.5" />
        </span>
        <span className="truncate text-[10px] uppercase text-muted-foreground">
          {label}
        </span>
      </div>
      <div className={`mt-1 truncate text-lg font-semibold ${valueCls}`}>
        {value}
      </div>
      <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
        {detail}
      </div>
    </div>
  );
}

function WbSignalGrid({ item }: { item: PriceRow }) {
  const discount = positivePercent(item.discount);
  const clubDiscount = positivePercent(item.club_discount);
  const clubPrice = clubDiscount
    ? priceRange(item.min_club_discounted_price, item.max_club_discounted_price)
    : "нет";
  const signals = [
    {
      icon: Tag,
      label: "Скидка WB",
      value: discount ? percentValue(discount) : "нет",
      detail: discount
        ? "из Prices & Discounts API"
        : item.currency_iso_code || "WB price list",
      tone: "default" as const,
    },
    {
      icon: SlidersHorizontal,
      label: "Цены по размерам",
      value: item.editable_size_price ? "включено" : "общая",
      detail: item.sizes_count
        ? `${item.sizes_count} размеров · ${priceRange(item.min_size_price, item.max_size_price)}`
        : "размерных строк нет",
      tone: item.editable_size_price ? ("info" as const) : ("default" as const),
    },
    {
      icon: ShieldCheck,
      label: "WB Club",
      value: clubDiscount ? percentValue(clubDiscount) : "нет",
      detail: clubDiscount ? clubPrice : "скидки WB Club нет",
      tone: "default" as const,
    },
    {
      icon: CalendarDays,
      label: "Акция WB",
      value: promotionSignalValue(item),
      detail: promotionSignalDetail(item),
      tone: !item.promotion_calendar_synced
        ? ("warning" as const)
        : (item.promotion_active_count ?? 0) > 0
          ? ("info" as const)
          : ("default" as const),
    },
    {
      icon: Calculator,
      label: "План акции",
      value: promotionPlanValue(item),
      detail: promotionPlanDetail(item),
      tone: promotionPlanTone(item),
    },
    {
      icon: ShieldAlert,
      label: "Защита WB",
      value: item.quarantine
        ? "карантин"
        : item.is_bad_turnover
          ? "низкая оборач."
          : hasWholesale(item)
            ? "B2B уровни"
            : "чисто",
      detail: item.quarantine
        ? `разница ${formatMoneyCompact(item.quarantine_price_diff)}`
        : hasWholesale(item)
          ? `${item.wholesale_discount_thresholds?.length ?? 0} уровней`
          : "блокирующих флагов нет",
      tone: item.quarantine
        ? ("danger" as const)
        : item.is_bad_turnover
          ? ("warning" as const)
          : ("default" as const),
    },
  ];
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {signals.map((signal) => (
        <SignalBox key={signal.label} {...signal} />
      ))}
    </div>
  );
}

function SignalBox({
  icon: Icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: typeof Tag;
  label: string;
  value: string;
  detail: string;
  tone: "default" | "info" | "warning" | "danger";
}) {
  const wrapCls =
    tone === "danger"
      ? "border-destructive/30 border-l-destructive bg-destructive/5"
      : tone === "warning"
        ? "border-warning/35 border-l-warning bg-warning/10"
        : tone === "info"
          ? "border-primary/30 border-l-primary bg-primary/5"
          : "border-border/80 border-l-border bg-background";
  const iconCls =
    tone === "danger"
      ? "bg-destructive/10 text-destructive"
      : tone === "warning"
        ? "bg-warning/15 text-warning"
        : tone === "info"
          ? "bg-primary/10 text-primary"
          : "bg-muted text-muted-foreground";
  const valueCls =
    tone === "danger"
      ? "text-destructive"
      : tone === "warning"
        ? "text-warning"
        : tone === "info"
          ? "text-primary"
          : "text-foreground";
  return (
    <div
      className={`min-w-0 rounded-md border border-l-4 px-3 py-2.5 shadow-sm ${wrapCls}`}
    >
      <div className="flex min-w-0 items-start gap-2.5">
        <div
          className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${iconCls}`}
        >
          <Icon className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0">
          <div className="text-[10px] uppercase text-muted-foreground">
            {label}
          </div>
          <div className={`mt-0.5 truncate text-sm font-semibold ${valueCls}`}>
            {value}
          </div>
          <div className="mt-0.5 truncate text-xs text-muted-foreground">
            {detail}
          </div>
        </div>
      </div>
    </div>
  );
}

function PromotionBreakdown({ item }: { item: PriceRow }) {
  const rows = item.promotion_details ?? [];
  if (!item.promotion_calendar_synced) {
    return (
      <div className="rounded-md border border-l-4 border-warning/35 border-l-warning bg-warning/10 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-warning" />
          <div>
            <div className="text-[10px] uppercase text-muted-foreground">
              Акции WB
            </div>
            <div className="text-sm font-semibold text-warning">
              календарь не загружен
            </div>
          </div>
        </div>
      </div>
    );
  }
  if (!rows.length) {
    return (
      <div className="rounded-md border border-l-4 border-border/80 border-l-border bg-background px-3 py-2.5 shadow-sm">
        <div className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-muted-foreground" />
          <div>
            <div className="text-[10px] uppercase text-muted-foreground">
              Акции WB
            </div>
            <div className="text-sm font-semibold">нет подходящих акций</div>
          </div>
        </div>
      </div>
    );
  }
  const active = rows.filter((row) => row.status === "active").length;
  const scheduled = rows.filter((row) => row.status === "scheduled").length;
  const available = rows.filter((row) => row.status === "available").length;
  return (
    <section className="space-y-2">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <CalendarDays className="h-4 w-4 text-primary" />
            Акции WB
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            {rows.length} строк из Promotion Calendar
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {active ? (
            <Badge
              variant="outline"
              className="border-primary/35 bg-primary/5 text-[10px] text-primary"
            >
              участвует {active}
            </Badge>
          ) : null}
          {scheduled ? (
            <Badge
              variant="outline"
              className="border-warning/40 bg-warning/10 text-[10px] text-warning"
            >
              план {scheduled}
            </Badge>
          ) : null}
          {available ? (
            <Badge variant="outline" className="text-[10px]">
              доступно {available}
            </Badge>
          ) : null}
        </div>
      </div>
      <div className="space-y-2">
        {rows.map((promotion) => (
          <PromotionBreakdownRow
            key={`${promotion.promotion_id}-${promotion.status}-${promotion.in_action ? "in" : "out"}`}
            promotion={promotion}
          />
        ))}
      </div>
    </section>
  );
}

function PromotionBreakdownRow({ promotion }: { promotion: PromotionDetail }) {
  const tone = promotionDetailTone(promotion);
  const toneClass =
    tone === "danger"
      ? "border-destructive/35 border-l-destructive bg-destructive/5"
      : tone === "warning"
        ? "border-warning/40 border-l-warning bg-warning/10"
        : tone === "info"
          ? "border-primary/30 border-l-primary bg-primary/5"
          : "border-border/80 border-l-border bg-background";
  const iconClass =
    tone === "danger"
      ? "bg-destructive/10 text-destructive"
      : tone === "warning"
        ? "bg-warning/15 text-warning"
        : tone === "info"
          ? "bg-primary/10 text-primary"
          : "bg-muted text-muted-foreground";
  const planClass =
    tone === "danger"
      ? "text-destructive"
      : tone === "warning"
        ? "text-warning"
        : tone === "info"
          ? "text-primary"
          : "text-foreground";
  return (
    <article
      className={`min-w-0 rounded-md border border-l-4 p-3 shadow-sm ${toneClass}`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 gap-3">
          <div
            className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${iconClass}`}
          >
            <CalendarDays className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge
                variant="outline"
                className={`h-5 text-[10px] ${promotionStatusClass(promotion.status)}`}
              >
                {promotionStatusLabel(promotion.status)}
              </Badge>
              <span className="font-mono text-[10px] text-muted-foreground">
                #{promotion.promotion_id}
              </span>
            </div>
            <div
              className="mt-1 break-words text-sm font-semibold leading-5"
              title={promotion.name ?? ""}
            >
              {promotion.name ?? "Без названия"}
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              {promotionDateRange(promotion)}
            </div>
          </div>
        </div>
        <div className="shrink-0 rounded-md bg-background/80 px-3 py-2 text-left sm:min-w-[136px] sm:text-right">
          <div className={`text-sm font-semibold ${planClass}`}>
            {promotionDetailPlanValue(promotion)}
          </div>
          <div className="text-xs text-muted-foreground">
            {promotion.plan_price
              ? `план ${formatMoneyCompact(promotion.plan_price)}`
              : "planPrice нет"}
          </div>
        </div>
      </div>
      <div className="mt-3 grid overflow-hidden rounded-md border border-border/70 bg-border/70 sm:grid-cols-5">
        <PromotionMetric
          label="WB price"
          value={formatMoney(promotion.price)}
        />
        <PromotionMetric
          label="planPrice"
          value={formatMoney(promotion.plan_price)}
          tone={
            tone === "danger"
              ? "danger"
              : tone === "warning"
                ? "warning"
                : undefined
          }
        />
        <PromotionMetric
          label="discount"
          value={promotionDiscountLine(promotion)}
        />
        <PromotionMetric
          label="до нуля"
          value={formatMoneyCompact(promotion.plan_safe_gap)}
          tone={(promotion.plan_safe_gap ?? 0) < 0 ? "danger" : "success"}
        />
        <PromotionMetric
          label="до цели"
          value={formatMoneyCompact(promotion.plan_target_gap)}
          tone={(promotion.plan_target_gap ?? 0) < 0 ? "warning" : "success"}
        />
      </div>
      <div className="mt-2 text-xs leading-5 text-muted-foreground">
        {promotionStatsLine(promotion)}
      </div>
      {promotion.advantages?.length ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {promotion.advantages.slice(0, 4).map((value) => (
            <Badge key={value} variant="secondary" className="h-5 text-[10px]">
              {value}
            </Badge>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function PromotionMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "danger" | "warning" | "success";
}) {
  const cls =
    tone === "danger"
      ? "text-destructive"
      : tone === "warning"
        ? "text-warning"
        : tone === "success"
          ? "text-success"
          : "";
  return (
    <div className="min-w-0 bg-background px-2.5 py-2">
      <div className="text-[9px] uppercase text-muted-foreground">{label}</div>
      <div className={`mt-0.5 truncate text-xs font-semibold ${cls}`}>
        {value}
      </div>
    </div>
  );
}

function StateBadge({ state }: { state: ReturnType<typeof safetyState> }) {
  const meta =
    state === "risk"
      ? {
          label: "ниже break-even",
          cls: "border-destructive/35 bg-destructive/5 text-destructive",
          icon: ShieldAlert,
        }
      : state === "target"
        ? {
            label: "ниже target",
            cls: "border-warning/40 bg-warning/10 text-warning",
            icon: TrendingUp,
          }
        : state === "safe"
          ? {
              label: "в норме",
              cls: "border-success/35 bg-success/5 text-success",
              icon: ShieldCheck,
            }
          : {
              label: "нет расчёта",
              cls: "border-primary/35 bg-primary/5 text-primary",
              icon: Database,
            };
  const Icon = meta.icon;
  return (
    <Badge variant="outline" className={`shrink-0 ${meta.cls}`}>
      <Icon className="mr-1 h-3 w-3" />
      {meta.label}
    </Badge>
  );
}

function PriceDetailSheet({
  item,
  accountId,
  dateFrom,
  dateTo,
  onClose,
}: {
  item: PriceRow | null;
  accountId: number | null;
  dateFrom: string;
  dateTo: string;
  onClose: () => void;
}) {
  const ref = referencePrice(item);
  return (
    <Sheet open={!!item} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="flex w-full flex-col overflow-hidden p-0 sm:max-w-[880px] xl:max-w-[960px]">
        {item ? (
          <>
            <div className="border-b bg-background/95 px-5 pb-4 pt-5 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/90">
              <SheetHeader className="space-y-2 pr-10 text-left">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <SheetTitle className="break-words pr-1 text-base leading-6 sm:text-lg">
                      {item.title ?? item.vendor_code ?? "Pricing detail"}
                    </SheetTitle>
                    <SheetDescription className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-mono">
                        {item.nm_id ? `nm_id ${item.nm_id}` : "SKU"}
                      </span>
                      <span>{item.vendor_code}</span>
                      <span>
                        {dateFrom} - {dateTo}
                      </span>
                    </SheetDescription>
                  </div>
                  <StateBadge state={safetyState(item)} />
                </div>
              </SheetHeader>
              <div className="mt-4">
                <DetailSummaryRail item={item} />
              </div>
            </div>

            <Tabs
              defaultValue="source"
              className="flex min-h-0 flex-1 flex-col"
            >
              <div className="border-b bg-background px-5 py-3">
                <TabsList className="grid h-10 w-full grid-cols-4 rounded-md bg-muted/70 p-1">
                  <TabsTrigger
                    className="h-8 rounded-sm text-xs"
                    value="economics"
                  >
                    Экономика
                  </TabsTrigger>
                  <TabsTrigger
                    className="h-8 rounded-sm text-xs"
                    value="source"
                  >
                    WB API
                  </TabsTrigger>
                  <TabsTrigger
                    className="h-8 rounded-sm text-xs"
                    value="formula"
                  >
                    Формула
                  </TabsTrigger>
                  <TabsTrigger
                    className="h-8 rounded-sm text-xs"
                    value="simulate"
                  >
                    Симуляция
                  </TabsTrigger>
                </TabsList>
              </div>

              <ScrollArea className="min-h-0 flex-1">
                <div className="px-5 py-4">
                  <TabsContent value="economics" className="mt-0 space-y-4">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <PanelValue
                        label="Цена WB"
                        value={formatMoney(item.current_price)}
                      />
                      <PanelValue
                        label="Со скидкой"
                        value={formatMoney(item.current_discounted_price)}
                      />
                      <PanelValue
                        label="Опорная цена"
                        value={formatMoney(ref)}
                      />
                      <PanelValue
                        label="Средняя продажа"
                        value={formatMoney(item.average_sale_price)}
                      />
                      <PanelValue
                        label="Цена до нуля"
                        value={formatMoney(item.break_even_price)}
                      />
                      <PanelValue
                        label="Цена цели"
                        value={formatMoney(item.target_margin_price)}
                      />
                      <PanelValue
                        label="Запас до нуля"
                        value={formatMoney(item.safe_price_gap)}
                        tone={
                          (item.safe_price_gap ?? 0) < 0 ? "danger" : "success"
                        }
                      />
                      <PanelValue
                        label="Запас до цели"
                        value={formatMoney(targetGap(item))}
                        tone={
                          (targetGap(item) ?? 0) < 0 ? "warning" : "success"
                        }
                      />
                    </div>
                    <MarginRail item={item} />
                  </TabsContent>

                  <TabsContent value="source" className="mt-0 space-y-4">
                    <WbSignalGrid item={item} />
                    <PromotionBreakdown item={item} />
                    <section className="space-y-2">
                      <div className="flex items-center gap-2 text-sm font-semibold">
                        <Database className="h-4 w-4 text-muted-foreground" />
                        Источники и расчёт
                      </div>
                      <div className="grid gap-2 sm:grid-cols-2">
                        <SourceBox
                          label="Источник цены"
                          value={sourceLabel(item.price_source)}
                          status={item.mapping_status ?? "unknown"}
                        />
                        <SourceBox
                          label="Расчёт"
                          value={item.calculation_state ?? "unknown"}
                          status={item.confidence ?? "unknown"}
                        />
                        <SourceBox
                          label="Данные"
                          value={item.data_state ?? "unknown"}
                          status={reasonText(item) || "ready"}
                        />
                        <SourceBox
                          label="Себестоимость"
                          value="настройки владельца"
                          status={item.estimated ? "estimated" : "computed"}
                        />
                        <SourceBox
                          label="WB price range"
                          value={priceRange(
                            item.min_size_price,
                            item.max_size_price,
                          )}
                          status={`${item.sizes_count ?? 0} размерных строк`}
                        />
                        <SourceBox
                          label="Цена со скидкой"
                          value={priceRange(
                            item.min_discounted_price,
                            item.max_discounted_price,
                          )}
                          status={
                            positivePercent(item.discount)
                              ? `скидка WB ${percentValue(item.discount)}`
                              : "скидки WB нет"
                          }
                        />
                        <SourceBox
                          label="Цена WB Club"
                          value={priceRange(
                            item.min_club_discounted_price,
                            item.max_club_discounted_price,
                          )}
                          status={
                            positivePercent(item.club_discount)
                              ? `WB Club ${percentValue(item.club_discount)}`
                              : "скидки WB Club нет"
                          }
                        />
                        <SourceBox
                          label="B2B скидки"
                          value={
                            hasWholesale(item)
                              ? `${item.wholesale_discount_thresholds?.length ?? 0} уровней`
                              : "не задано"
                          }
                          status={
                            hasWholesale(item)
                              ? "поле wholesaleDiscountThreshold"
                              : "wholesaleDiscountThreshold нет"
                          }
                        />
                        <SourceBox
                          label="План акции"
                          value={formatMoney(item.promotion_min_plan_price)}
                          status={promotionPlanDetail(item)}
                        />
                      </div>
                    </section>
                    {hasWbAttention(item) ? (
                      <Alert className="border-primary/30 bg-primary/5">
                        <Tag className="h-4 w-4 text-primary" />
                        <AlertTitle>WB сигналы цены</AlertTitle>
                        <AlertDescription>
                          Скидка, акция, цены по размерам, карантин, низкая
                          оборачиваемость и B2B уровни могут менять безопасный
                          сценарий перед изменением цены.
                        </AlertDescription>
                      </Alert>
                    ) : null}
                    {reasonText(item) ? (
                      <Alert className="border-warning/35 bg-warning/10">
                        <AlertTriangle className="h-4 w-4 text-warning" />
                        <AlertTitle>Blocker</AlertTitle>
                        <AlertDescription>{reasonText(item)}</AlertDescription>
                      </Alert>
                    ) : null}
                  </TabsContent>

                  <TabsContent value="formula" className="mt-0 space-y-3">
                    <FormulaLine
                      label="Reference price"
                      value={formatMoney(ref)}
                    />
                    <FormulaLine
                      label="Break-even price"
                      value={formatMoney(item.break_even_price)}
                    />
                    <FormulaLine
                      label="Target margin price"
                      value={formatMoney(item.target_margin_price)}
                    />
                    <FormulaLine
                      label="Break-even gap"
                      value={`${formatMoney(ref)} - ${formatMoney(item.break_even_price)} = ${formatMoney(item.safe_price_gap)}`}
                    />
                    <FormulaLine
                      label="Target gap"
                      value={`${formatMoney(ref)} - ${formatMoney(item.target_margin_price)} = ${formatMoney(targetGap(item))}`}
                    />
                    <FormulaLine
                      label="Margin at current price"
                      value={formatPercent(
                        item.estimated_margin_at_current_price ??
                          item.estimated_margin_percent,
                      )}
                    />
                  </TabsContent>

                  <TabsContent value="simulate" className="mt-0">
                    <SimulationInline
                      item={item}
                      accountId={accountId}
                      dateFrom={dateFrom}
                      dateTo={dateTo}
                    />
                  </TabsContent>
                </div>
              </ScrollArea>
            </Tabs>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function MarginRail({ item }: { item: PriceRow }) {
  const safeGap = num(item.safe_price_gap);
  const tGap = targetGap(item);
  const state = safetyState(item);
  const safePct =
    safeGap == null ? 0 : Math.max(0, Math.min(100, 50 + safeGap / 200));
  const targetPct =
    tGap == null ? 0 : Math.max(0, Math.min(100, 50 + tGap / 200));
  return (
    <div className="rounded-md border border-border/70 bg-background p-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="flex items-center gap-2 font-medium">
          <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" />
          Safety rail
        </span>
        <StateBadge state={state} />
      </div>
      <div className="space-y-3">
        <RailRow label="Break-even" value={safePct} amount={safeGap} />
        <RailRow label="Target margin" value={targetPct} amount={tGap} />
      </div>
    </div>
  );
}

function RailRow({
  label,
  value,
  amount,
}: {
  label: string;
  value: number;
  amount: number | null;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span
          className={(amount ?? 0) < 0 ? "text-destructive" : "text-success"}
        >
          {formatMoneyCompact(amount)}
        </span>
      </div>
      <Progress value={value} className="h-1.5" />
    </div>
  );
}

function SourceBox({
  label,
  value,
  status,
}: {
  label: string;
  value: string;
  status: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-border/70 bg-muted/20 px-3 py-2.5 shadow-sm">
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 truncate font-medium">{value}</div>
      <div className="mt-1 truncate text-xs text-muted-foreground">
        {status}
      </div>
    </div>
  );
}

function FormulaLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border/70 bg-background px-3 py-2.5 shadow-sm sm:flex-row sm:items-center sm:justify-between">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-mono text-xs font-medium">{value}</span>
    </div>
  );
}

function SimulationInline({
  item,
  accountId,
  dateFrom,
  dateTo,
  compact = false,
}: {
  item: PriceRow;
  accountId: number | null;
  dateFrom: string;
  dateTo: string;
  compact?: boolean;
}) {
  const initial = referencePrice(item) ?? item.current_price ?? 0;
  const [price, setPrice] = useState(String(Math.round(initial || 0)));
  const [dropPct, setDropPct] = useState("0");
  const [result, setResult] = useState<PriceSimulationResult | null>(null);
  const itemKey = rowKey(item);

  useEffect(() => {
    setPrice(String(Math.round(initial || 0)));
    setDropPct("0");
    setResult(null);
  }, [initial, itemKey]);

  const mutation = useMutation({
    mutationFn: () =>
      simulatePricing({
        account_id: accountId,
        nm_id: item.nm_id,
        sku_id: item.sku_id,
        date_from: dateFrom,
        date_to: dateTo,
        price: Number(price || initial || 0),
        sales_drop_assumption_percent: Number(dropPct || 0),
      }) as Promise<PriceSimulationResult>,
    onSuccess: (data) => setResult(data),
    onError: (error: Error) => toast.error(error.message),
  });

  const disabled = !accountId || !item.sku_id || !Number(price);
  return (
    <div className="rounded-md border bg-background p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Calculator className="h-4 w-4 text-muted-foreground" />
          Симуляция
        </div>
        {compact ? (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant="outline" className="text-[10px]">
                  what-if
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                Цена и падение продаж пересчитывают прибыль.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : null}
      </div>
      <div className={compact ? "grid gap-2" : "grid gap-3 sm:grid-cols-2"}>
        <div>
          <Label className="text-xs">Новая цена</Label>
          <Input
            className="mt-1 h-9"
            type="number"
            value={price}
            onChange={(event) => setPrice(event.target.value)}
          />
        </div>
        <div>
          <Label className="text-xs">Падение продаж, %</Label>
          <Input
            className="mt-1 h-9"
            type="number"
            value={dropPct}
            onChange={(event) => setDropPct(event.target.value)}
          />
        </div>
      </div>
      <Button
        className="mt-3 w-full"
        size="sm"
        disabled={disabled || mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending ? (
          <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
        ) : (
          <Calculator className="mr-1.5 h-4 w-4" />
        )}
        Посчитать
      </Button>
      {result ? (
        <div className="mt-3 grid gap-2 text-xs">
          <ResultLine
            label="Выручка"
            value={formatMoney(result.expected_revenue)}
          />
          <ResultLine
            label="Прибыль"
            value={formatMoney(result.expected_profit)}
            danger={Number(result.expected_profit) < 0}
          />
          <ResultLine
            label="Маржа"
            value={formatPercent(result.expected_margin_percent)}
            danger={Number(result.expected_margin_percent) < 0}
          />
          <ResultLine
            label="Риск"
            value={result.risk_flag || "ok"}
            danger={Boolean(result.risk_flag && result.risk_flag !== "ok")}
          />
        </div>
      ) : null}
    </div>
  );
}

function ResultLine({
  label,
  value,
  danger,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="flex items-center justify-between rounded-md bg-muted/40 px-2 py-1.5">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={`font-medium tabular-nums ${danger ? "text-destructive" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}

function EmptyQueue({ search }: { search: string }) {
  return (
    <div className="flex min-h-[340px] items-center justify-center px-4 py-10 text-center">
      <div className="max-w-sm">
        <Search className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
        <div className="text-sm font-medium">
          {search ? "Ничего не найдено" : "Очередь пустая"}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          {search
            ? "Проверьте nm_id, SKU или vendor_code."
            : "В текущем срезе нет SKU для выбранного фильтра."}
        </div>
      </div>
    </div>
  );
}

function PricingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {[1, 2, 3, 4].map((item) => (
          <Skeleton key={item} className="h-28 rounded-md" />
        ))}
      </div>
      <Skeleton className="h-[520px] rounded-md" />
    </div>
  );
}
