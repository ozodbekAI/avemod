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
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
  current_sku: "карточка SKU",
  wb_price_snapshot: "цены WB",
  article_price: "цена товара",
  average_sale: "средняя продажа",
  missing: "цены нет",
};

const REASON_LABELS: Record<string, string> = {
  missing_cost: "нет себестоимости",
  missing_price: "нет цены",
  not_enough_units: "нет продаж",
  revenue_not_available: "нет выручки",
  formula_not_computable: "формула недоступна",
};

const STATUS_LABELS: Record<string, string> = {
  blocked: "заблокировано",
  computed: "рассчитано",
  estimated: "оценка",
  final: "финально",
  high: "высокая уверенность",
  low: "низкая уверенность",
  mapped: "связано",
  medium: "средняя уверенность",
  missing: "нет данных",
  not_computable: "нет расчёта",
  partial: "частично",
  provisional: "предварительно",
  ready: "готово",
  synced: "синхронизировано",
  unknown: "статус не указан",
  unmapped: "не связано",
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
  const [autoOpenedNmId, setAutoOpenedNmId] = useState<string | null>(null);
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

  useEffect(() => {
    const nmId = routeSearch.nm_id ?? null;
    if (!nmId) {
      setAutoOpenedNmId(null);
      return;
    }
    if (!selectedItem || autoOpenedNmId === nmId) return;
    if (String(selectedItem.nm_id ?? "") !== nmId) return;
    setSheetItem(selectedItem);
    setAutoOpenedNmId(nmId);
  }, [autoOpenedNmId, routeSearch.nm_id, selectedItem]);

  const trustInputs = moneyQ.data ? trustInputsFromSummary(moneyQ.data) : null;
  const normTrust = normalizeTrust(moneyQ.data);
  const isLoading = overviewQ.isLoading || listQ.isLoading;
  const isFetching = overviewQ.isFetching || listQ.isFetching;

  return (
    <PageShell>
      <PageHeader
        title="Цены и акции"
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
          <AlertTitle>Ошибка загрузки цен</AlertTitle>
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
          <PricingOverview
            stats={stats}
            overview={overview}
            view={view}
            onViewChange={setView}
          />

          {stats.notComputable > 0 ? (
            <Alert className="border-warning/35 bg-warning/10">
              <AlertTriangle className="h-4 w-4 text-warning" />
              <AlertTitle>Очередь расчёта не полная</AlertTitle>
              <AlertDescription>
                {stats.notComputable} SKU без расчёта. Главный источник
                блокировки — себестоимость.{" "}
                <Link
                  to="/costs"
                  className="font-medium underline underline-offset-2"
                >
                  Открыть себестоимость
                </Link>
              </AlertDescription>
            </Alert>
          ) : null}

          <PricingQueueWorkbench
            items={items}
            total={listQ.data?.total ?? items.length}
            page={page}
            search={search}
            debouncedSearch={debouncedSearch}
            view={view}
            stats={stats}
            isFetching={listQ.isFetching}
            onSearchChange={setSearch}
            onViewChange={setView}
            onPrevPage={() => setPage((current) => Math.max(0, current - 1))}
            onNextPage={() => setPage((current) => current + 1)}
            onOpenItem={(item) => {
              setSelectedKey(rowKey(item));
              setSheetItem(item);
            }}
            canPrevPage={page > 0}
            canNextPage={items.length >= PAGE_SIZE}
          />
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

function statusLabel(status: unknown): string {
  const key = String(status ?? "unknown")
    .trim()
    .toLowerCase();
  if (!key) return STATUS_LABELS.unknown;
  return STATUS_LABELS[key] ?? key.replace(/_/g, " ").replace(/\s+/g, " ");
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
  return "по календарю акций";
}

function promotionSignalValue(item: PriceRow | null | undefined): string {
  if (!item?.promotion_calendar_synced) return "нет данных";
  if ((item.promotion_active_count ?? 0) > 0) return "участвует";
  if ((item.promotion_available_count ?? 0) > 0) return "доступна";
  return "не участвует";
}

function promotionSignalDetail(item: PriceRow | null | undefined): string {
  if (!item?.promotion_calendar_synced) {
    return "календарь акций не загружен";
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
    item.promo_type ? `тип ${item.promo_type}` : null,
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

function PricingOverview({
  stats,
  overview,
  view,
  onViewChange,
}: {
  stats: ReturnType<typeof normalizeStats>;
  overview: PricePage;
  view: ViewKey;
  onViewChange: (value: ViewKey) => void;
}) {
  const targetOnly =
    Math.max(0, stats.belowTargetMargin - stats.belowBE) ||
    stats.belowTargetMargin;
  const promoRisk = stats.promotionPlanBelowBE + stats.promotionPlanBelowTarget;
  const coverage = Math.max(
    0,
    Math.min(100, overview.trusted_revenue_cost_coverage_percent ?? 0),
  );
  const final = overview.financial_final === true;

  return (
    <section className="overflow-hidden rounded-lg border bg-card shadow-sm">
      <div className="flex flex-col gap-3 border-b px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <BarChart3 className="h-4 w-4 text-primary" />
            Рабочий контур цен
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Сначала риски маржи, затем скидки, акции и качество данных.
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="gap-1.5">
            <Database className="h-3.5 w-3.5 text-primary" />
            цены · акции · продажи · финансы
          </Badge>
          <Badge
            variant="outline"
            className={
              final
                ? "border-success/30 bg-success/5 text-success"
                : "border-warning/35 bg-warning/10 text-warning"
            }
          >
            {final ? "финальные данные" : "предварительные данные"}
          </Badge>
        </div>
      </div>

      <div className="grid gap-px bg-border md:grid-cols-2 xl:grid-cols-5">
        <OverviewMetric
          label="Ниже нуля"
          value={stats.belowBE}
          detail={stats.belowBE ? "срочно поднять цену" : "критичных нет"}
          icon={stats.belowBE ? ShieldAlert : ShieldCheck}
          tone={stats.belowBE ? "danger" : "success"}
          active={view === "risk"}
          onClick={() => onViewChange(view === "risk" ? "all" : "risk")}
        />
        <OverviewMetric
          label="Ниже цели"
          value={targetOnly}
          detail="не добирает маржу"
          icon={TrendingUp}
          tone={targetOnly ? "warning" : "success"}
          active={view === "margin_watch"}
          onClick={() =>
            onViewChange(view === "margin_watch" ? "all" : "margin_watch")
          }
        />
        <OverviewMetric
          label="Нет расчёта"
          value={stats.notComputable}
          detail={`${percent(stats.notComputable, stats.total)} очереди`}
          icon={Database}
          tone={stats.notComputable ? "info" : "success"}
          active={view === "not_computable"}
          onClick={() =>
            onViewChange(view === "not_computable" ? "all" : "not_computable")
          }
        />
        <OverviewMetric
          label="Риск акции"
          value={promoRisk}
          detail={
            stats.promotionPlanBelowBE
              ? `${stats.promotionPlanBelowBE} ниже нуля`
              : promoRisk
                ? `${stats.promotionPlanBelowTarget} ниже цели`
                : `${stats.promotionAvailable} доступно`
          }
          icon={CalendarDays}
          tone={
            stats.promotionPlanBelowBE
              ? "danger"
              : promoRisk
                ? "warning"
                : "success"
          }
        />
        <OverviewCoverage
          value={coverage}
          blockers={overview.financial_final_blockers_total ?? 0}
          final={final}
        />
      </div>

      <div className="grid gap-px bg-border md:grid-cols-3 xl:grid-cols-6">
        <OverviewSignal
          label="Размерные цены"
          value={stats.editableSizePrice}
          detail="индивидуальные цены"
          icon={SlidersHorizontal}
        />
        <OverviewSignal
          label="Низкая оборач."
          value={stats.badTurnover}
          detail="флаг WB"
          icon={AlertTriangle}
          tone={stats.badTurnover ? "warning" : "muted"}
        />
        <OverviewSignal
          label="Карантин"
          value={stats.quarantine}
          detail="цена заблокирована"
          icon={ShieldAlert}
          tone={stats.quarantine ? "danger" : "muted"}
        />
        <OverviewSignal
          label="B2B уровни"
          value={stats.wholesaleDiscount}
          detail="оптовые скидки"
          icon={Tag}
        />
        <OverviewSignal
          label="Участвует"
          value={stats.promotionActive}
          detail="активные акции"
          icon={CalendarDays}
        />
        <OverviewSignal
          label="Безопасный план"
          value={stats.promotionPlanSafe}
          detail="акция не режет маржу"
          icon={Calculator}
          tone={stats.promotionPlanSafe ? "success" : "muted"}
        />
      </div>
    </section>
  );
}

function OverviewMetric({
  label,
  value,
  detail,
  icon: Icon,
  tone,
  active,
  onClick,
}: {
  label: string;
  value: number;
  detail: string;
  icon: typeof AlertTriangle;
  tone: "danger" | "warning" | "info" | "success";
  active?: boolean;
  onClick?: () => void;
}) {
  const toneClass =
    tone === "danger"
      ? "text-destructive"
      : tone === "warning"
        ? "text-warning"
        : tone === "info"
          ? "text-primary"
          : "text-success";
  const bgClass =
    tone === "danger"
      ? "bg-destructive/5"
      : tone === "warning"
        ? "bg-warning/10"
        : tone === "info"
          ? "bg-primary/5"
          : "bg-success/5";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`group min-h-[104px] bg-card px-4 py-3 text-left transition hover:bg-muted/40 ${
        active ? "bg-primary/5 ring-1 ring-inset ring-primary/30" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[11px] uppercase text-muted-foreground">
            {label}
          </div>
          <div
            className={`mt-1 text-3xl font-semibold tabular-nums ${toneClass}`}
          >
            {value}
          </div>
        </div>
        <span
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${bgClass} ${toneClass}`}
        >
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <div className="mt-2 truncate text-xs text-muted-foreground">
        {detail}
      </div>
    </button>
  );
}

function OverviewCoverage({
  value,
  blockers,
  final,
}: {
  value: number;
  blockers: number;
  final: boolean;
}) {
  return (
    <div className="min-h-[104px] bg-card px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[11px] uppercase text-muted-foreground">
            Себестоимость
          </div>
          <div className="mt-1 text-3xl font-semibold tabular-nums">
            {value.toFixed(1)}%
          </div>
        </div>
        <Badge
          variant="outline"
          className={
            final
              ? "border-success/30 bg-success/5 text-success"
              : "border-warning/35 bg-warning/10 text-warning"
          }
        >
          {final ? "финально" : "проверка"}
        </Badge>
      </div>
      <Progress value={value} className="mt-3 h-1.5" />
      <div className="mt-2 truncate text-xs text-muted-foreground">
        {blockers
          ? `покрытие затрат · ${blockers} блокеров`
          : "покрытие затрат · блокеров нет"}
      </div>
    </div>
  );
}

function OverviewSignal({
  label,
  value,
  detail,
  icon: Icon,
  tone = "info",
}: {
  label: string;
  value: number;
  detail: string;
  icon: typeof Tag;
  tone?: "info" | "success" | "warning" | "danger" | "muted";
}) {
  const toneClass =
    tone === "danger"
      ? "text-destructive"
      : tone === "warning"
        ? "text-warning"
        : tone === "success"
          ? "text-success"
          : tone === "muted"
            ? "text-muted-foreground"
            : "text-primary";

  return (
    <div className="flex min-h-[68px] items-center justify-between gap-3 bg-card px-4 py-2.5">
      <div className="min-w-0">
        <div className="truncate text-[10px] uppercase text-muted-foreground">
          {label}
        </div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground">
          {detail}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Icon className={`h-4 w-4 ${toneClass}`} />
        <span className="text-lg font-semibold tabular-nums">{value}</span>
      </div>
    </div>
  );
}

function PricingQueueWorkbench({
  items,
  total,
  page,
  search,
  debouncedSearch,
  view,
  stats,
  isFetching,
  onSearchChange,
  onViewChange,
  onPrevPage,
  onNextPage,
  onOpenItem,
  canPrevPage,
  canNextPage,
}: {
  items: PriceRow[];
  total: number;
  page: number;
  search: string;
  debouncedSearch: string;
  view: ViewKey;
  stats: ReturnType<typeof normalizeStats>;
  isFetching: boolean;
  onSearchChange: (value: string) => void;
  onViewChange: (value: ViewKey) => void;
  onPrevPage: () => void;
  onNextPage: () => void;
  onOpenItem: (item: PriceRow) => void;
  canPrevPage: boolean;
  canNextPage: boolean;
}) {
  return (
    <section className="overflow-hidden rounded-lg border bg-card shadow-sm">
      <div className="border-b px-4 py-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <SlidersHorizontal className="h-4 w-4 text-primary" />
              Очередь решений
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {total} SKU · строки отсортированы по риску цены и маржи
            </div>
          </div>
          <div className="relative w-full lg:w-[360px]">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Найти nm_id, SKU или артикул"
              className="h-9 pl-8 text-xs"
            />
          </div>
        </div>
        <ViewSwitcher value={view} onChange={onViewChange} stats={stats} />
      </div>

      {items.length ? (
        <>
          <div className="hidden lg:block">
            <Table>
              <TableHeader className="bg-muted/35">
                <TableRow className="hover:bg-muted/35">
                  <TableHead className="w-[118px] pl-4">Решение</TableHead>
                  <TableHead>Товар</TableHead>
                  <TableHead className="w-[150px] text-right">Цена</TableHead>
                  <TableHead className="w-[130px] text-right">Маржа</TableHead>
                  <TableHead className="w-[180px]">Запас</TableHead>
                  <TableHead className="w-[190px]">Акции</TableHead>
                  <TableHead className="w-[104px] pr-4 text-right">
                    Разбор
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <PricingTableRow
                    key={rowKey(item)}
                    item={item}
                    onOpen={() => onOpenItem(item)}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="divide-y lg:hidden">
            {items.map((item) => (
              <PricingMobileRow
                key={rowKey(item)}
                item={item}
                onOpen={() => onOpenItem(item)}
              />
            ))}
          </div>
        </>
      ) : (
        <EmptyQueue search={debouncedSearch} />
      )}

      <div className="flex items-center justify-between border-t px-4 py-2 text-xs text-muted-foreground">
        <span>
          Страница {page + 1} · показано {items.length}
        </span>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="h-8 px-2"
            disabled={!canPrevPage || isFetching}
            onClick={onPrevPage}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8 px-2"
            disabled={!canNextPage || isFetching}
            onClick={onNextPage}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </section>
  );
}

function PricingTableRow({
  item,
  onOpen,
}: {
  item: PriceRow;
  onOpen: () => void;
}) {
  const ref = referencePrice(item);
  const safeGap = num(item.safe_price_gap);
  const tGap = targetGap(item);
  const margin =
    num(item.estimated_margin_at_current_price) ??
    num(item.estimated_margin_percent);
  const state = safetyState(item);

  return (
    <TableRow
      data-pricing-row="true"
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
      className="group cursor-pointer"
    >
      <TableCell className="pl-4">
        <StateBadge state={state} />
      </TableCell>
      <TableCell>
        <ProductCell item={item} />
      </TableCell>
      <TableCell className="text-right">
        <div className="font-semibold tabular-nums">{priceRange(ref, ref)}</div>
        <div className="mt-1 flex justify-end gap-1">
          <DiscountPills item={item} />
        </div>
      </TableCell>
      <TableCell className="text-right">
        <div
          className={`font-semibold tabular-nums ${margin != null && margin < 0 ? "text-destructive" : ""}`}
        >
          {formatPercent(margin)}
        </div>
        <div className="text-[11px] text-muted-foreground">
          {statusLabel(item.confidence)}
        </div>
      </TableCell>
      <TableCell>
        <GapStack safeGap={safeGap} targetGapValue={tGap} />
      </TableCell>
      <TableCell>
        <PromotionCell item={item} />
      </TableCell>
      <TableCell className="pr-4 text-right">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 gap-1.5"
          onClick={(event) => {
            event.stopPropagation();
            onOpen();
          }}
        >
          <FileSearch className="h-3.5 w-3.5" />
          Открыть
        </Button>
      </TableCell>
    </TableRow>
  );
}

function PricingMobileRow({
  item,
  onOpen,
}: {
  item: PriceRow;
  onOpen: () => void;
}) {
  const ref = referencePrice(item);
  const safeGap = num(item.safe_price_gap);
  const tGap = targetGap(item);
  const margin =
    num(item.estimated_margin_at_current_price) ??
    num(item.estimated_margin_percent);

  return (
    <button
      type="button"
      data-pricing-row="true"
      onClick={onOpen}
      className="block w-full px-4 py-3 text-left transition hover:bg-muted/40"
    >
      <div className="flex items-start justify-between gap-3">
        <ProductCell item={item} />
        <StateBadge state={safetyState(item)} />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <MiniMetric label="Цена" value={priceRange(ref, ref)} />
        <MiniMetric
          label="Маржа"
          value={formatPercent(margin)}
          danger={margin != null && margin < 0}
        />
        <MiniMetric
          label="До цели"
          value={formatMoneyCompact(tGap)}
          danger={(tGap ?? 0) < 0}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <DiscountPills item={item} />
        <PromotionTiny item={item} />
        {safeGap != null && safeGap < 0 ? (
          <Badge
            variant="outline"
            className="border-destructive/35 bg-destructive/5 text-[10px] text-destructive"
          >
            до нуля {formatMoneyCompact(safeGap)}
          </Badge>
        ) : null}
      </div>
    </button>
  );
}

function ProductCell({ item }: { item: PriceRow }) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-xs font-semibold">
          {item.nm_id ?? "—"}
        </span>
        {item.sku_id ? (
          <span className="text-[11px] text-muted-foreground">
            SKU {item.sku_id}
          </span>
        ) : null}
      </div>
      <div
        className="mt-0.5 line-clamp-1 text-sm font-medium"
        title={item.title ?? item.vendor_code ?? ""}
      >
        {item.title ?? item.vendor_code ?? "Без названия"}
      </div>
      <div className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
        {item.vendor_code ?? "артикул не указан"}
      </div>
    </div>
  );
}

function DiscountPills({ item }: { item: PriceRow }) {
  const discount = positivePercent(item.discount);
  const clubDiscount = positivePercent(item.club_discount);
  return (
    <>
      {discount ? (
        <Badge variant="secondary" className="h-5 text-[10px]">
          скидка {percentValue(discount)}
        </Badge>
      ) : null}
      {clubDiscount ? (
        <Badge
          variant="outline"
          className="h-5 border-primary/25 bg-primary/5 text-[10px] text-primary"
        >
          клубная скидка {percentValue(clubDiscount)}
        </Badge>
      ) : null}
    </>
  );
}

function GapStack({
  safeGap,
  targetGapValue,
}: {
  safeGap: number | null;
  targetGapValue: number | null;
}) {
  return (
    <div className="space-y-1 text-xs">
      <div className="flex items-center justify-between gap-3">
        <span className="text-muted-foreground">До нуля</span>
        <span
          className={`font-semibold tabular-nums ${(safeGap ?? 0) < 0 ? "text-destructive" : "text-success"}`}
        >
          {formatMoneyCompact(safeGap)}
        </span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-muted-foreground">До цели</span>
        <span
          className={`font-semibold tabular-nums ${(targetGapValue ?? 0) < 0 ? "text-warning" : "text-success"}`}
        >
          {formatMoneyCompact(targetGapValue)}
        </span>
      </div>
    </div>
  );
}

function PromotionCell({ item }: { item: PriceRow }) {
  return (
    <div className="min-w-0 space-y-1">
      <PromotionTiny item={item} />
      <div className="truncate text-xs text-muted-foreground">
        {promotionPlanDetail(item)}
      </div>
    </div>
  );
}

function PromotionTiny({ item }: { item: PriceRow }) {
  const tone = promotionPlanTone(item);
  const cls =
    tone === "danger"
      ? "border-destructive/35 bg-destructive/5 text-destructive"
      : tone === "warning"
        ? "border-warning/40 bg-warning/10 text-warning"
        : tone === "info"
          ? "border-primary/30 bg-primary/5 text-primary"
          : "border-border text-muted-foreground";
  return (
    <Badge variant="outline" className={`h-5 max-w-full text-[10px] ${cls}`}>
      <span className="truncate">
        {promotionSignalValue(item)} · {promotionPlanValue(item)}
      </span>
    </Badge>
  );
}

function MiniMetric({
  label,
  value,
  danger,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="min-w-0 rounded-md border bg-muted/20 px-2 py-1.5">
      <div className="truncate text-[10px] uppercase text-muted-foreground">
        {label}
      </div>
      <div
        className={`mt-0.5 truncate text-xs font-semibold tabular-nums ${
          danger ? "text-destructive" : ""
        }`}
      >
        {value}
      </div>
    </div>
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

type SignalTone = "default" | "info" | "warning" | "danger";

type PriceSignal = {
  icon: typeof Tag;
  label: string;
  value: string;
  detail: string;
  tone: SignalTone;
};

function WbSignalGrid({ item }: { item: PriceRow }) {
  const discount = positivePercent(item.discount);
  const clubDiscount = positivePercent(item.club_discount);
  const clubPrice = clubDiscount
    ? priceRange(item.min_club_discounted_price, item.max_club_discounted_price)
    : "нет";
  const currentSignals: PriceSignal[] = [
    {
      icon: Tag,
      label: "Текущая скидка",
      value: discount ? percentValue(discount) : "нет",
      detail: discount
        ? "цена продавца"
        : item.currency_iso_code || "без скидки",
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
      label: "Клубная скидка",
      value: clubDiscount ? percentValue(clubDiscount) : "нет",
      detail: clubDiscount ? clubPrice : "клубной скидки нет",
      tone: "default" as const,
    },
  ];
  const promoSignals: PriceSignal[] = [
    {
      icon: CalendarDays,
      label: "Акции",
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
      label: "Плановая цена",
      value: promotionPlanValue(item),
      detail: promotionPlanDetail(item),
      tone: promotionPlanTone(item),
    },
    {
      icon: ShieldAlert,
      label: "Ограничения",
      value: item.quarantine
        ? "карантин"
        : item.is_bad_turnover
          ? "низкая оборач."
          : hasWholesale(item)
            ? "B2B уровни"
            : "нет",
      detail: item.quarantine
        ? `разница ${formatMoneyCompact(item.quarantine_price_diff)}`
        : hasWholesale(item)
          ? `${item.wholesale_discount_thresholds?.length ?? 0} уровней`
          : "ограничений нет",
      tone: item.quarantine
        ? ("danger" as const)
        : item.is_bad_turnover
          ? ("warning" as const)
          : ("default" as const),
    },
  ];
  return (
    <div className="space-y-3">
      <SignalGroup title="Текущие условия" signals={currentSignals} />
      <SignalGroup title="Промо и ограничения" signals={promoSignals} />
    </div>
  );
}

function SignalGroup({
  title,
  signals,
}: {
  title: string;
  signals: PriceSignal[];
}) {
  return (
    <section className="space-y-2">
      <div className="text-xs font-medium text-muted-foreground">{title}</div>
      <div className="grid gap-2 sm:grid-cols-2">
        {signals.map((signal) => (
          <SignalBox key={signal.label} {...signal} />
        ))}
      </div>
    </section>
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
  tone: SignalTone;
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
              Акции и промо
            </div>
            <div className="text-sm font-semibold text-warning">
              календарь акций не загружен
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
              Акции и промо
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
            Акции и промо
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            {rows.length} строк из календаря акций
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
              : "плановой цены нет"}
          </div>
        </div>
      </div>
      <div className="mt-3 grid overflow-hidden rounded-md border border-border/70 bg-border/70 sm:grid-cols-5">
        <PromotionMetric
          label="Цена сейчас"
          value={formatMoney(promotion.price)}
        />
        <PromotionMetric
          label="План акции"
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
          label="Скидка"
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
          label: "ниже нуля",
          cls: "border-destructive/35 bg-destructive/5 text-destructive",
          icon: ShieldAlert,
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
  const safeGap = num(item?.safe_price_gap);
  const tGap = targetGap(item);
  const margin =
    num(item?.estimated_margin_at_current_price) ??
    num(item?.estimated_margin_percent);
  const state = safetyState(item);
  return (
    <Sheet open={!!item} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="flex w-full flex-col overflow-hidden p-0 sm:max-w-[min(1180px,calc(100vw-3rem))]">
        {item ? (
          <div className="flex min-h-0 flex-1 flex-col bg-background">
            <div className="border-b px-5 pb-4 pt-5">
              <SheetHeader className="space-y-2 pr-10 text-left">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <SheetTitle className="break-words pr-1 text-lg leading-6 sm:text-xl">
                      {item.title ?? item.vendor_code ?? "Детали цены"}
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
              <div className="mt-4 grid overflow-hidden rounded-lg border bg-border md:grid-cols-4">
                <ReviewMetric
                  icon={Tag}
                  label="Цена покупателя"
                  value={formatMoneyCompact(ref)}
                  detail={sourceLabel(item.price_source)}
                />
                <ReviewMetric
                  icon={TrendingUp}
                  label="Маржа"
                  value={formatPercent(margin)}
                  detail={statusLabel(
                    item.confidence ?? item.calculation_state,
                  )}
                  tone={margin != null && margin < 0 ? "danger" : "default"}
                />
                <ReviewMetric
                  icon={ShieldCheck}
                  label="Запас до нуля"
                  value={formatMoneyCompact(safeGap)}
                  detail={
                    safeGap != null && safeGap < 0
                      ? "цена ниже себестоимости"
                      : "себестоимость покрыта"
                  }
                  tone={safeGap != null && safeGap < 0 ? "danger" : "success"}
                />
                <ReviewMetric
                  icon={CalendarDays}
                  label="План акции"
                  value={
                    item.promotion_min_plan_price
                      ? formatMoneyCompact(item.promotion_min_plan_price)
                      : "нет"
                  }
                  detail={promotionPlanValue(item)}
                  tone={promotionPlanTone(item)}
                />
              </div>
            </div>

            <Tabs
              defaultValue="summary"
              className="flex min-h-0 flex-1 flex-col"
            >
              <div className="border-b bg-background px-5 py-3">
                <TabsList className="grid h-auto w-full grid-cols-2 rounded-md bg-muted/70 p-1 md:grid-cols-5">
                  <TabsTrigger
                    className="h-8 rounded-sm text-xs"
                    value="summary"
                  >
                    Решение
                  </TabsTrigger>
                  <TabsTrigger
                    className="h-8 rounded-sm text-xs"
                    value="discounts"
                  >
                    Скидки
                  </TabsTrigger>
                  <TabsTrigger className="h-8 rounded-sm text-xs" value="promo">
                    Акции
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
                    Что если
                  </TabsTrigger>
                </TabsList>
              </div>

              <ScrollArea className="min-h-0 flex-1">
                <div className="px-5 py-4">
                  <TabsContent value="summary" className="mt-0 space-y-4">
                    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
                      <section className="space-y-4">
                        <DecisionNarrative item={item} />
                        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                          <PanelValue
                            label="Цена до скидки"
                            value={formatMoney(item.current_price)}
                          />
                          <PanelValue
                            label="Со скидкой"
                            value={formatMoney(item.current_discounted_price)}
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
                            value={formatMoney(safeGap)}
                            tone={
                              safeGap != null && safeGap < 0
                                ? "danger"
                                : "success"
                            }
                          />
                          <PanelValue
                            label="Запас до цели"
                            value={formatMoney(tGap)}
                            tone={
                              tGap != null && tGap < 0 ? "warning" : "success"
                            }
                          />
                          <PanelValue
                            label="Средняя продажа"
                            value={formatMoney(item.average_sale_price)}
                          />
                          <PanelValue
                            label="Источник цены"
                            value={sourceLabel(item.price_source)}
                          />
                        </div>
                        <MarginRail item={item} />
                      </section>
                      <section className="space-y-3 rounded-lg border bg-muted/20 p-3">
                        <div className="flex items-center gap-2 text-sm font-semibold">
                          <FileSearch className="h-4 w-4 text-primary" />
                          Карта решения
                        </div>
                        <DecisionChecklist item={item} />
                        <div className="flex flex-wrap gap-2">
                          {item.nm_id ? (
                            <Button asChild size="sm" variant="outline">
                              <Link
                                to="/products/$nmId"
                                params={{ nmId: String(item.nm_id) }}
                              >
                                <ArrowRight className="mr-1.5 h-4 w-4" />
                                Карточка товара
                              </Link>
                            </Button>
                          ) : null}
                        </div>
                      </section>
                    </div>
                  </TabsContent>

                  <TabsContent value="discounts" className="mt-0 space-y-4">
                    <WbSignalGrid item={item} />
                    {hasWbAttention(item) ? (
                      <Alert className="border-primary/30 bg-primary/5">
                        <Tag className="h-4 w-4 text-primary" />
                        <AlertTitle>Условия перед изменением цены</AlertTitle>
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
                        <AlertTitle>Нужно заполнить данные</AlertTitle>
                        <AlertDescription>{reasonText(item)}</AlertDescription>
                      </Alert>
                    ) : null}
                  </TabsContent>

                  <TabsContent value="promo" className="mt-0">
                    <PromotionBreakdown item={item} />
                  </TabsContent>

                  <TabsContent value="formula" className="mt-0 space-y-3">
                    <DataAuditGrid item={item} />
                    <FormulaLine
                      label="Опорная цена"
                      value={formatMoney(ref)}
                    />
                    <FormulaLine
                      label="Цена до нуля"
                      value={formatMoney(item.break_even_price)}
                    />
                    <FormulaLine
                      label="Цена для цели"
                      value={formatMoney(item.target_margin_price)}
                    />
                    <FormulaLine
                      label="Запас до нуля"
                      value={`${formatMoney(ref)} - ${formatMoney(item.break_even_price)} = ${formatMoney(item.safe_price_gap)}`}
                    />
                    <FormulaLine
                      label="Запас до цели"
                      value={`${formatMoney(ref)} - ${formatMoney(item.target_margin_price)} = ${formatMoney(targetGap(item))}`}
                    />
                    <FormulaLine
                      label="Маржа сейчас"
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
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function ReviewMetric({
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
  const toneClass =
    tone === "danger"
      ? "text-destructive"
      : tone === "warning"
        ? "text-warning"
        : tone === "info"
          ? "text-primary"
          : tone === "success"
            ? "text-success"
            : "text-foreground";
  const iconClass =
    tone === "danger"
      ? "bg-destructive/10 text-destructive"
      : tone === "warning"
        ? "bg-warning/15 text-warning"
        : tone === "info"
          ? "bg-primary/10 text-primary"
          : tone === "success"
            ? "bg-success/10 text-success"
            : "bg-muted text-muted-foreground";
  return (
    <div className="min-w-0 bg-card px-4 py-3">
      <div className="flex min-w-0 items-center gap-2">
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${iconClass}`}
        >
          <Icon className="h-3.5 w-3.5" />
        </span>
        <span className="truncate text-[10px] uppercase text-muted-foreground">
          {label}
        </span>
      </div>
      <div className={`mt-2 truncate text-xl font-semibold ${toneClass}`}>
        {value}
      </div>
      <div className="mt-0.5 truncate text-xs text-muted-foreground">
        {detail}
      </div>
    </div>
  );
}

function DecisionNarrative({ item }: { item: PriceRow }) {
  const state = safetyState(item);
  const safeGap = num(item.safe_price_gap);
  const tGap = targetGap(item);
  const title =
    state === "risk"
      ? "Цена ниже себестоимости"
      : state === "target"
        ? "Маржа ниже целевой"
        : state === "safe"
          ? "Цена проходит экономику"
          : "Расчёт пока неполный";
  const text =
    state === "risk"
      ? `До нуля не хватает ${formatMoneyCompact(Math.abs(safeGap ?? 0))}. Сначала проверьте себестоимость и план акции.`
      : state === "target"
        ? `До цели не хватает ${formatMoneyCompact(Math.abs(tGap ?? 0))}. Цена не убыточная, но маржа ниже нормы.`
        : state === "safe"
          ? "Можно менять цену только после проверки скидок, акций и ограничений WB."
          : reasonText(item) || "Не хватает данных для безопасного решения.";
  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-sm font-semibold">{title}</div>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
            {text}
          </p>
        </div>
        <StateBadge state={state} />
      </div>
    </section>
  );
}

function DecisionChecklist({ item }: { item: PriceRow }) {
  const rows = [
    {
      label: "Экономика",
      ok: safetyState(item) === "safe",
      text:
        safetyState(item) === "safe"
          ? "запас есть"
          : reasonText(item) || "нужна проверка цены",
    },
    {
      label: "Скидки",
      ok: Boolean(positivePercent(item.discount)),
      text: positivePercent(item.discount)
        ? `продавец ${percentValue(item.discount)}`
        : "скидка не задана",
    },
    {
      label: "Акции",
      ok:
        item.promotion_calendar_synced === true && !hasPromotionPlanRisk(item),
      text: promotionPlanDetail(item),
    },
    {
      label: "Ограничения",
      ok: !item.quarantine && !item.is_bad_turnover,
      text: item.quarantine
        ? "карантин цены"
        : item.is_bad_turnover
          ? "низкая оборачиваемость"
          : "блокировок нет",
    },
  ];
  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div
          key={row.label}
          className="flex items-start gap-2 rounded-md border bg-background px-3 py-2"
        >
          {row.ok ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          )}
          <div className="min-w-0">
            <div className="text-xs font-medium">{row.label}</div>
            <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
              {row.text}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function DataAuditGrid({ item }: { item: PriceRow }) {
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Database className="h-4 w-4 text-muted-foreground" />
        Проверка данных
      </div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        <SourceBox
          label="Источник цены"
          value={sourceLabel(item.price_source)}
          status={statusLabel(item.mapping_status)}
        />
        <SourceBox
          label="Расчёт"
          value={statusLabel(item.calculation_state)}
          status={statusLabel(item.confidence)}
        />
        <SourceBox
          label="Данные"
          value={statusLabel(item.data_state)}
          status={reasonText(item) || "готово"}
        />
        <SourceBox
          label="Себестоимость"
          value="настройки владельца"
          status={item.estimated ? "оценка" : "рассчитано"}
        />
        <SourceBox
          label="Диапазон цен"
          value={priceRange(item.min_size_price, item.max_size_price)}
          status={`${item.sizes_count ?? 0} размерных строк`}
        />
        <SourceBox
          label="B2B скидки"
          value={
            hasWholesale(item)
              ? `${item.wholesale_discount_thresholds?.length ?? 0} уровней`
              : "не задано"
          }
          status={hasWholesale(item) ? "оптовые уровни" : "оптовых уровней нет"}
        />
      </div>
    </section>
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
          Запас маржи
        </span>
        <StateBadge state={state} />
      </div>
      <div className="space-y-3">
        <RailRow label="До нуля" value={safePct} amount={safeGap} />
        <RailRow label="До цели" value={targetPct} amount={tGap} />
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
                  сценарий
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
