import { useDateRange } from "@/lib/date-range-context";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  keepPreviousData,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useEffect, useMemo, useState, type ComponentType } from "react";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ArrowRight,
  BarChart3,
  CalendarDays,
  ChevronRight,
  CircleDollarSign,
  Eye,
  Filter,
  Layers3,
  LineChart,
  PackageSearch,
  Pause,
  RefreshCw,
  Search,
  ShieldAlert,
  Target,
  TrendingDown,
  TrendingUp,
  WalletCards,
  Wrench,
} from "lucide-react";
import { useAccounts } from "@/lib/account-context";
import { fetchAdsEfficiency } from "@/lib/money-endpoints";
import { moneySummaryQueryOptions } from "@/lib/queries/money-summary";
import { api } from "@/lib/api";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { cn } from "@/lib/utils";
import {
  formatDate,
  formatDateTime,
  formatMoney,
  formatMoneyCompact,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import { EndpointError } from "@/components/EndpointError";
import { TrustStatusBanner } from "@/components/money-ui/TrustStatusBanner";
import {
  AllocationStatusBadge,
  ClusterEmptyNotice,
  GranularityBadge,
} from "@/components/granularity";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { ActionCenterReturnLink } from "@/components/action-center/ActionCenterReturnLink";
import { routeSearchText } from "@/lib/action-center-routing";

type RowFilter =
  | "all"
  | "high_drr"
  | "spend_no_sales"
  | "profitable"
  | "loss"
  | "allocation";
type AdsHintFilter =
  | "all"
  | "AD_PAUSE_REVIEW"
  | "AD_SCALE_REVIEW"
  | "AD_ALLOCATION_REVIEW"
  | "WATCH"
  | "DATA_FIX";
type SortMode =
  | "spend"
  | "drr"
  | "profit"
  | "clicks"
  | "cr"
  | "orders"
  | "canceled"
  | "spend_share";
type SortDirection = "asc" | "desc";

type AdsSearch = {
  focus?: "allocation";
  rowFilter?: RowFilter;
  hint?: AdsHintFilter;
  sort?: SortMode;
  problem_instance_id?: string;
  nm_id?: number;
};

type Tone = "default" | "success" | "warning" | "danger" | "info";

type AdCampaign = {
  id: number;
  account_id: number;
  advert_id: number;
  campaign_type?: number | null;
  status?: number | null;
  bid_type?: string | null;
  name?: string | null;
  change_time?: string | null;
  payload?: Record<string, unknown>;
  items?: CampaignItem[];
};

type CampaignItem = {
  id: number;
  nm_id?: number | null;
  name?: string | null;
  payload?: Record<string, unknown>;
};

type AdStat = {
  id: number;
  advert_id: number;
  stat_date: string;
  nm_id?: number | null;
  views?: number | null;
  clicks?: number | null;
  ctr?: number | null;
  cr?: number | null;
  cpc?: number | null;
  cpm?: number | null;
  atbs?: number | null;
  orders?: number | null;
  shks?: number | null;
  sum?: number | null;
  sum_price?: number | null;
  canceled?: number | null;
  payload?: Record<string, unknown>;
};

type AdCluster = {
  id: number;
  advert_id: number;
  stat_date: string;
  cluster?: string | null;
  nm_id?: number | null;
  views?: number | null;
  clicks?: number | null;
  ctr?: number | null;
  cpc?: number | null;
  cpm?: number | null;
  atbs?: number | null;
  orders?: number | null;
  shks?: number | null;
  sum?: number | null;
  avg_position?: number | null;
  payload?: Record<string, unknown>;
};

type AdsRecord = Record<string, unknown>;

type AdsTrendPoint = {
  date: string;
  label: string;
  spend: number;
  revenue: number;
  views: number;
  clicks: number;
  orders: number;
  shks: number;
  atbs: number;
  canceled: number;
  drr: number | null;
  ctr: number | null;
  cr: number | null;
  cpc: number | null;
};

type TrendComparison = {
  recentDays: number;
  previousDays: number;
  spendChange: number | null;
  ordersChange: number | null;
  drrChange: number | null;
  recentSpend: number;
  recentRevenue: number;
  recentOrders: number;
  recentDrr: number | null;
  forecastSpend7d: number;
  forecastRevenue7d: number;
  forecastOrders7d: number;
  forecastDrr7d: number | null;
};

type ClusterAggregate = {
  key: string;
  spend: number;
  views: number;
  clicks: number;
  orders: number;
  shks: number;
  avgPosition: number | null;
};

type ApiPage<T> = {
  total?: number | null;
  limit?: number | null;
  offset?: number | null;
  items?: T[];
  rows?: T[];
  articles?: T[];
  summary?: AdsRecord;
  meta?: AdsRecord;
  computed_at?: string | null;
  cache_status?: string | null;
};

type AdsEfficiencyResponse = ApiPage<AdsRecord>;

type MoneySummaryLike = AdsRecord & {
  kpis?: AdsRecord;
  meta?: AdsRecord;
  answer?: { business_status?: string | null };
  operational_trusted?: boolean | null;
  financial_final?: boolean | null;
  open_issues_total?: number | null;
};

type EnrichedRow = {
  key: string;
  raw: AdsRecord;
  skuId: number | null;
  nmId: number | null;
  title: string;
  vendorCode: string | null;
  level: string;
  advertId: number | null;
  advertIds: number[];
  campaignName: string;
  campaignCount: number;
  campaign?: AdCampaign;
  views: number;
  clicks: number;
  orders: number;
  shks: number;
  atbs: number;
  canceled: number;
  ctr: number | null;
  cr: number | null;
  cpc: number | null;
  adRevenue: number;
  businessRevenue: number;
  spendShare: number | null;
  revenue: number;
  adSpend: number;
  rawAdSpend: number;
  sourceAdSpend: number;
  overallocatedAdSpend: number;
  unallocatedAdSpend: number;
  drr: number | null;
  profitAfterAds: number | null;
  stockQty: number | null;
  daysOfStock: number | null;
  allocationStatus: string;
  allocationLabel: string;
  finalProfitAllowed: boolean;
  confidence: string;
  trustState: string;
  blockedReasons: string[];
  hint: Exclude<AdsHintFilter, "all">;
};

export const Route = createFileRoute("/_authenticated/ads")({
  component: AdsPage,
  validateSearch: (s: Record<string, unknown>): AdsSearch => {
    const rawFilter = routeSearchText(s.rowFilter);
    const rowFilter =
      rawFilter === "all" ||
      rawFilter === "high_drr" ||
      rawFilter === "spend_no_sales" ||
      rawFilter === "profitable" ||
      rawFilter === "loss" ||
      rawFilter === "allocation"
        ? rawFilter
        : rawFilter === "overallocated_or_unallocated"
          ? "allocation"
          : undefined;
    const hint = routeSearchText(s.hint);
    const sort = routeSearchText(s.sort);
    const nmIdText = routeSearchText(s.nm_id);
    const nmId =
      nmIdText && /^\d+$/.test(nmIdText) ? Number(nmIdText) : undefined;
    return {
      focus: s.focus === "allocation" ? "allocation" : undefined,
      rowFilter,
      hint:
        hint === "all" ||
        hint === "AD_PAUSE_REVIEW" ||
        hint === "AD_SCALE_REVIEW" ||
        hint === "AD_ALLOCATION_REVIEW" ||
        hint === "WATCH" ||
        hint === "DATA_FIX"
          ? hint
          : undefined,
      sort:
        sort === "spend" ||
        sort === "drr" ||
        sort === "profit" ||
        sort === "clicks" ||
        sort === "cr" ||
        sort === "orders" ||
        sort === "canceled" ||
        sort === "spend_share"
          ? sort
          : undefined,
      problem_instance_id: routeSearchText(s.problem_instance_id),
      nm_id: nmId,
    };
  },
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

const PAGE_SIZE = 60;

const HINT_COPY: Record<
  Exclude<AdsHintFilter, "all">,
  {
    label: string;
    short: string;
    tone: Tone;
    icon: ComponentType<{ className?: string }>;
  }
> = {
  AD_PAUSE_REVIEW: {
    label: "Проверить / остановить рекламу",
    short: "Пауза",
    tone: "danger",
    icon: Pause,
  },
  AD_SCALE_REVIEW: {
    label: "Можно масштабировать",
    short: "Рост",
    tone: "success",
    icon: TrendingUp,
  },
  AD_ALLOCATION_REVIEW: {
    label: "Проверить разнос рекламы",
    short: "Разнос",
    tone: "warning",
    icon: Layers3,
  },
  WATCH: { label: "Наблюдать", short: "Наблюдать", tone: "info", icon: Eye },
  DATA_FIX: {
    label: "Сначала исправить данные",
    short: "Данные",
    tone: "warning",
    icon: Wrench,
  },
};

const FILTERS: Array<{
  value: RowFilter;
  label: string;
  icon: ComponentType<{ className?: string }>;
}> = [
  { value: "all", label: "Все", icon: Filter },
  { value: "high_drr", label: "Высокий ДРР", icon: ShieldAlert },
  { value: "spend_no_sales", label: "Расход без продаж", icon: TrendingDown },
  { value: "profitable", label: "В плюс", icon: TrendingUp },
  { value: "loss", label: "В минус", icon: AlertTriangle },
  { value: "allocation", label: "Разнос", icon: Layers3 },
];

const SORTS: Array<{
  value: SortMode;
  label: string;
  icon: ComponentType<{ className?: string }>;
}> = [
  { value: "spend", label: "Расход", icon: WalletCards },
  { value: "drr", label: "ДРР", icon: Target },
  { value: "profit", label: "Прибыль", icon: CircleDollarSign },
  { value: "clicks", label: "Клики", icon: BarChart3 },
];

const ROW_SORT_HEADERS: Array<{
  value: SortMode;
  label: string;
  icon: ComponentType<{ className?: string }>;
}> = [
  { value: "spend", label: "Затраты", icon: WalletCards },
  { value: "drr", label: "ДРР", icon: Target },
  { value: "profit", label: "Прибыль", icon: CircleDollarSign },
  { value: "clicks", label: "Клики", icon: BarChart3 },
  { value: "cr", label: "CR", icon: Target },
  { value: "orders", label: "Заказы", icon: PackageSearch },
  { value: "canceled", label: "Отмены", icon: AlertTriangle },
  { value: "spend_share", label: "Доля", icon: Layers3 },
];

function AdsPage() {
  const { activeId } = useAccounts();
  const { from: monthAgo, to: today } = useDateRange();
  const routeSearch = Route.useSearch();

  return (
    <PageShell>
      <PageHeader
        title="WB Реклама"
        description="Расходы, ДРР, прибыль после рекламы и качество привязки к карточкам."
      />

      <ActionCenterReturnLink
        problem_instance_id={routeSearch.problem_instance_id}
        nm_id={routeSearch.nm_id}
        className="mb-4"
      />

      {activeId ? (
        <DataDependencyNotice
          accountId={activeId}
          domains={["ads", "sales", "orders", "finance", "product_cards"]}
        />
      ) : null}

      {!activeId ? (
        <Alert>
          <AlertTitle>Не выбран кабинет</AlertTitle>
          <AlertDescription>Выберите кабинет в шапке.</AlertDescription>
        </Alert>
      ) : (
        <AdsWorkbench accountId={activeId} dateFrom={monthAgo} dateTo={today} />
      )}
    </PageShell>
  );
}

function AdsWorkbench({
  accountId,
  dateFrom,
  dateTo,
}: {
  accountId: number;
  dateFrom: string;
  dateTo: string;
}) {
  const routeSearch = Route.useSearch();
  const qc = useQueryClient();
  const [offset, setOffset] = useState(0);
  const routeNmId = routeSearch.nm_id;
  const routeNmIdText = routeNmId != null ? String(routeNmId) : "";
  const [search, setSearch] = useState(routeNmIdText);
  const [hintFilter, setHintFilter] = useState<AdsHintFilter>(
    routeSearch.hint ?? "all",
  );
  const [rowFilter, setRowFilter] = useState<RowFilter>(
    routeSearch.rowFilter ??
      (routeSearch.focus === "allocation" ? "allocation" : "all"),
  );
  const [sortMode, setSortMode] = useState<SortMode>(
    routeSearch.sort ?? "spend",
  );
  const [sortDir, setSortDir] = useState<SortDirection>("desc");
  const [selected, setSelected] = useState<EnrichedRow | null>(null);
  const productScopeNmId = routeNmIdText || undefined;
  const efficiencyLimit = productScopeNmId ? 200 : PAGE_SIZE;
  const efficiencyOffset = productScopeNmId ? 0 : offset;

  useEffect(() => {
    setOffset(0);
    setSelected(null);
  }, [accountId, dateFrom, dateTo]);

  useEffect(() => {
    if (routeSearch.rowFilter) setRowFilter(routeSearch.rowFilter);
    if (routeSearch.hint) setHintFilter(routeSearch.hint);
    if (routeSearch.sort) setSortMode(routeSearch.sort);
    if (routeNmIdText) setSearch(routeNmIdText);
    if (routeSearch.focus === "allocation" && !routeSearch.rowFilter)
      setRowFilter("allocation");
  }, [
    routeSearch.focus,
    routeSearch.hint,
    routeNmIdText,
    routeSearch.rowFilter,
    routeSearch.sort,
  ]);

  useEffect(() => {
    setOffset(0);
  }, [search, hintFilter, rowFilter, sortMode, sortDir]);

  const handleSort = (value: SortMode) => {
    if (sortMode === value) {
      setSortDir((direction) => (direction === "desc" ? "asc" : "desc"));
    } else {
      setSortDir("desc");
      setSortMode(value);
    }
  };

  const eff = useQuery<AdsEfficiencyResponse>({
    queryKey: [
      "ads-efficiency",
      accountId,
      dateFrom,
      dateTo,
      efficiencyLimit,
      efficiencyOffset,
      productScopeNmId ?? "",
    ],
    queryFn: () =>
      fetchAdsEfficiency({
        accountId,
        dateFrom,
        dateTo,
        limit: efficiencyLimit,
        offset: efficiencyOffset,
      }) as Promise<AdsEfficiencyResponse>,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const campaignsQ = useQuery<ApiPage<AdCampaign> | AdCampaign[]>({
    queryKey: ["ads-campaigns", accountId],
    queryFn: ({ signal }) =>
      api<ApiPage<AdCampaign> | AdCampaign[]>(API_ENDPOINTS.ads.campaigns, {
        query: { account_id: accountId, limit: 200 },
        signal,
      }),
    staleTime: 60_000,
  });

  const moneyQ = useQuery({
    ...moneySummaryQueryOptions({ accountId, dateFrom, dateTo }),
    retry: false,
    staleTime: 60_000,
  });

  const moneyData = moneyQ.data as MoneySummaryLike | undefined;
  const items = useMemo(() => pageItems<AdsRecord>(eff.data), [eff.data]);
  const campaigns = useMemo(
    () => pageItems<AdCampaign>(campaignsQ.data),
    [campaignsQ.data],
  );
  const campById = useMemo(() => {
    const map = new Map<number, AdCampaign>();
    for (const campaign of campaigns) {
      const advertId = num(campaign.advert_id);
      if (advertId != null) map.set(advertId, campaign);
    }
    return map;
  }, [campaigns]);

  const enriched = useMemo(
    () => items.map((item, index) => enrichAdsRow(item, index, campById)),
    [campById, items],
  );

  const summary = (eff.data?.summary ?? eff.data?.meta ?? {}) as AdsRecord;
  const totalRows =
    num(eff.data?.total) ?? num(summary.total_count) ?? enriched.length;
  const moneyK = moneyData?.kpis ?? moneyData ?? {};
  const ownerRevenue = num(moneyK.revenue ?? moneyData?.revenue);
  const finalAdSpend = num(
    moneyK.ad_spend_final ?? moneyK.ad_spend ?? moneyK.ad_spend_finance,
  );
  const sourceSpend =
    num(moneyK.ads_source_spend) ??
    num(
      summary.source_ad_spend ??
        summary.ads_source_spend ??
        summary.total_spend,
    ) ??
    sum(enriched, (row) => row.sourceAdSpend);
  const allocatedSpend =
    num(moneyK.ads_allocated_spend) ??
    num(
      summary.allocated_ad_spend ??
        summary.ads_allocated_spend ??
        summary.allocated_spend,
    ) ??
    sum(enriched, (row) => row.adSpend);
  const overallocatedSpend =
    num(moneyK.ads_overallocated_spend) ??
    num(summary.overallocated_ad_spend ?? summary.ads_overallocated_spend) ??
    sum(enriched, (row) => row.overallocatedAdSpend);
  const unallocatedSpend =
    num(moneyK.ads_unallocated_spend) ??
    num(summary.unallocated_ad_spend ?? summary.ads_unallocated_spend) ??
    sum(enriched, (row) => row.unallocatedAdSpend);
  const totalRevenue =
    num(
      summary.source_revenue ??
        summary.ad_revenue ??
        summary.revenue ??
        summary.attributed_revenue,
    ) ?? sum(enriched, (row) => row.revenue);
  const totalDrr =
    num(moneyK.drr_total_percent) ??
    num(summary.drr_percent ?? summary.drr) ??
    (totalRevenue > 0
      ? ((sourceSpend || allocatedSpend) / totalRevenue) * 100
      : null);
  const profitAfterAds =
    num(moneyK.net_profit_after_ads) ??
    num(summary.profit_after_ads) ??
    (enriched.length ? sum(enriched, (row) => row.profitAfterAds ?? 0) : null);
  const totalViews = num(summary.views) ?? sum(enriched, (row) => row.views);
  const totalClicks = num(summary.clicks) ?? sum(enriched, (row) => row.clicks);
  const totalOrders = num(summary.orders) ?? sum(enriched, (row) => row.orders);
  const totalAtbs = num(summary.atbs) ?? sum(enriched, (row) => row.atbs);
  const totalShks = num(summary.shks) ?? sum(enriched, (row) => row.shks);
  const totalCanceled =
    num(summary.canceled) ?? sum(enriched, (row) => row.canceled);
  const totalCr =
    num(summary.cr_percent ?? summary.cr) ??
    (totalClicks > 0 ? (totalOrders / totalClicks) * 100 : null);
  const allocationStatus = normalizeAllocationStatus(
    overallocatedSpend > 0.01
      ? "overallocated"
      : (moneyK.ads_allocation_status ??
          summary.ads_allocation_status ??
          "matched"),
  );
  const allocationProgress =
    sourceSpend > 0 ? clamp((allocatedSpend / sourceSpend) * 100, 0, 100) : 0;
  const noSourceSpend =
    sourceSpend <= 0.01 && enriched.every((row) => row.adSpend <= 0.01);

  const filtered = useMemo(() => {
    let rows = enriched;
    if (hintFilter !== "all")
      rows = rows.filter((row) => row.hint === hintFilter);
    if (rowFilter !== "all") {
      rows = rows.filter((row) => {
        if (rowFilter === "high_drr") return row.drr != null && row.drr >= 25;
        if (rowFilter === "spend_no_sales")
          return row.adSpend > 0 && row.revenue <= 0;
        if (rowFilter === "profitable") return (row.profitAfterAds ?? 0) > 0;
        if (rowFilter === "loss")
          return row.profitAfterAds != null && row.profitAfterAds < 0;
        if (rowFilter === "allocation") {
          return (
            row.allocationStatus !== "matched" ||
            row.overallocatedAdSpend > 0.01 ||
            row.unallocatedAdSpend > 0.01 ||
            !row.finalProfitAllowed
          );
        }
        return true;
      });
    }
    const q = search.trim().toLowerCase();
    if (q) {
      rows = rows.filter((row) =>
        [
          row.title,
          row.vendorCode,
          row.nmId,
          row.skuId,
          row.advertId,
          row.advertIds.join(","),
          row.campaignName,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(q)),
      );
    }
    return [...rows].sort((a, b) => compareAdsRows(a, b, sortMode, sortDir));
  }, [enriched, hintFilter, rowFilter, search, sortDir, sortMode]);
  const hasScopedFilters =
    Boolean(search.trim()) || hintFilter !== "all" || rowFilter !== "all";
  const scopedRows = hasScopedFilters ? filtered : enriched;
  const scopedSourceSpend = hasScopedFilters
    ? sum(scopedRows, (row) => row.sourceAdSpend)
    : sourceSpend;
  const scopedAllocatedSpend = hasScopedFilters
    ? sum(scopedRows, (row) => row.adSpend)
    : allocatedSpend;
  const scopedOverallocatedSpend = hasScopedFilters
    ? sum(scopedRows, (row) => row.overallocatedAdSpend)
    : overallocatedSpend;
  const scopedUnallocatedSpend = hasScopedFilters
    ? sum(scopedRows, (row) => row.unallocatedAdSpend)
    : unallocatedSpend;
  const scopedRevenue = hasScopedFilters
    ? sum(scopedRows, (row) => row.revenue)
    : totalRevenue;
  const scopedDrr = hasScopedFilters
    ? scopedRevenue > 0
      ? ((scopedSourceSpend || scopedAllocatedSpend) / scopedRevenue) * 100
      : null
    : totalDrr;
  const scopedProfitAfterAds = hasScopedFilters
    ? scopedRows.some((row) => row.profitAfterAds != null)
      ? sum(scopedRows, (row) => row.profitAfterAds ?? 0)
      : null
    : profitAfterAds;
  const scopedViews = hasScopedFilters
    ? sum(scopedRows, (row) => row.views)
    : totalViews;
  const scopedClicks = hasScopedFilters
    ? sum(scopedRows, (row) => row.clicks)
    : totalClicks;
  const scopedOrders = hasScopedFilters
    ? sum(scopedRows, (row) => row.orders)
    : totalOrders;
  const scopedAtbs = hasScopedFilters
    ? sum(scopedRows, (row) => row.atbs)
    : totalAtbs;
  const scopedShks = hasScopedFilters
    ? sum(scopedRows, (row) => row.shks)
    : totalShks;
  const scopedCanceled = hasScopedFilters
    ? sum(scopedRows, (row) => row.canceled)
    : totalCanceled;
  const scopedCr = hasScopedFilters
    ? scopedClicks > 0
      ? (scopedOrders / scopedClicks) * 100
      : null
    : totalCr;
  const scopedAllocationStatus = hasScopedFilters
    ? normalizeAllocationStatus(
        scopedOverallocatedSpend > 0.01
          ? "overallocated"
          : scopedUnallocatedSpend > 0.01
            ? "partial"
            : scopedRows.length
              ? "matched"
              : allocationStatus,
      )
    : allocationStatus;
  const scopedAllocationProgress =
    scopedSourceSpend > 0
      ? clamp((scopedAllocatedSpend / scopedSourceSpend) * 100, 0, 100)
      : 0;
  const scopedNoSourceSpend =
    scopedSourceSpend <= 0.01 && scopedRows.every((row) => row.adSpend <= 0.01);
  const scopedFinalSpend = hasScopedFilters
    ? scopedAllocatedSpend
    : (finalAdSpend ?? scopedAllocatedSpend);
  const scopedCpc =
    scopedClicks > 0 && scopedSourceSpend > 0
      ? scopedSourceSpend / scopedClicks
      : null;
  const scopedSpendShare =
    sourceSpend > 0 ? (scopedSourceSpend / sourceSpend) * 100 : null;
  const scopedOwnerDrr =
    !hasScopedFilters &&
    finalAdSpend != null &&
    ownerRevenue != null &&
    ownerRevenue > 0
      ? (finalAdSpend / ownerRevenue) * 100
      : scopedDrr;
  const spendReconciliationDiff =
    !hasScopedFilters && finalAdSpend != null
      ? scopedSourceSpend - finalAdSpend
      : 0;
  const hasSpendReconciliationGap =
    Math.abs(spendReconciliationDiff) > 1 && !hasScopedFilters;
  const scopedCampaignCount = hasScopedFilters
    ? new Set(
        scopedRows.flatMap((row) =>
          row.advertIds.length
            ? row.advertIds
            : row.advertId != null
              ? [row.advertId]
              : [],
        ),
      ).size
    : campaigns.length;
  const scopedSearchLabel = search.trim();

  if (eff.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28 rounded-lg" />
        <div className="grid gap-3 md:grid-cols-4">
          {[1, 2, 3, 4].map((item) => (
            <Skeleton key={item} className="h-24 rounded-lg" />
          ))}
        </div>
        {[1, 2, 3].map((item) => (
          <Skeleton key={item} className="h-24 rounded-lg" />
        ))}
      </div>
    );
  }

  if (eff.isError) {
    return (
      <Alert variant="destructive" className="mt-3">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Ошибка загрузки рекламы</AlertTitle>
        <AlertDescription>
          <Button
            size="sm"
            className="mt-3"
            onClick={() => eff.refetch()}
            disabled={eff.isFetching}
          >
            <RefreshCw
              className={cn(
                "mr-2 h-3.5 w-3.5",
                eff.isFetching && "animate-spin",
              )}
            />
            Повторить
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-lg border bg-card">
        <div className="h-1 bg-primary" />
        <div className="flex flex-col gap-4 p-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
              <Target className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold tracking-tight">
                  WB Ads control
                </h2>
                <Badge
                  variant="outline"
                  className="border-primary/30 bg-primary/5 text-primary"
                >
                  {formatDate(dateFrom)} - {formatDate(dateTo)}
                </Badge>
                {scopedSearchLabel ? (
                  <Badge variant="outline">nm {scopedSearchLabel}</Badge>
                ) : null}
                <AllocationStatusBadge status={scopedAllocationStatus} />
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>
                  {formatNumber(hasScopedFilters ? filtered.length : totalRows)}{" "}
                  позиций{hasScopedFilters ? " по фильтру" : ""}
                </span>
                <span>{formatNumber(scopedCampaignCount)} кампаний</span>
                <span>
                  {eff.data?.computed_at
                    ? formatDateTime(eff.data.computed_at)
                    : "расчёт текущего периода"}
                </span>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                qc.invalidateQueries({
                  predicate: (query) =>
                    String(query.queryKey[0]).startsWith("ads-"),
                });
                qc.invalidateQueries({ queryKey: ["money-summary"] });
              }}
              disabled={eff.isFetching || campaignsQ.isFetching}
            >
              <RefreshCw
                className={cn(
                  "mr-2 h-3.5 w-3.5",
                  (eff.isFetching || campaignsQ.isFetching) && "animate-spin",
                )}
              />
              Обновить
            </Button>
            <Button
              asChild
              size="sm"
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <Link to="/data-fix">
                <Wrench className="mr-2 h-3.5 w-3.5" />
                Данные
              </Link>
            </Button>
          </div>
        </div>
      </div>

      {routeSearch.focus === "allocation" ? (
        <Alert className="border-primary/25 bg-primary/5">
          <Layers3 className="h-4 w-4 text-primary" />
          <AlertTitle>Фокус: привязка рекламных расходов</AlertTitle>
          <AlertDescription>
            Показаны строки, где расход требует проверки перед финальной оценкой
            прибыли.
          </AlertDescription>
        </Alert>
      ) : null}

      {moneyData ? (
        <TrustStatusBanner
          trust={{
            operational_trusted: moneyData.operational_trusted ?? null,
            financial_final: moneyData.financial_final ?? null,
            business_status: moneyData.answer?.business_status ?? null,
          }}
          quality={{
            ads_allocation_status: scopedAllocationStatus,
            supplier_confirmed_cost_coverage_percent:
              moneyK?.supplier_confirmed_cost_coverage_percent ?? null,
            finance_reconciliation_status:
              moneyK?.finance_reconciliation_status ?? null,
            open_issues_total: moneyData.open_issues_total ?? null,
          }}
        />
      ) : null}

      {scopedAllocationStatus === "overallocated" ||
      scopedOverallocatedSpend > 0.01 ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Реклама распределена с предупреждением</AlertTitle>
          <AlertDescription>
            Переаллокация {formatMoney(scopedOverallocatedSpend)}. Прибыль после
            рекламы предварительная.
          </AlertDescription>
        </Alert>
      ) : null}

      {!scopedNoSourceSpend &&
      scopedUnallocatedSpend > 0.01 &&
      scopedAllocationStatus !== "overallocated" ? (
        <Alert className="border-warning/30 bg-warning/5">
          <AlertTriangle className="h-4 w-4 text-warning" />
          <AlertTitle>
            Не разнесено: {formatMoney(scopedUnallocatedSpend)}
          </AlertTitle>
          <AlertDescription>
            Часть рекламного расхода пока не привязана к карточкам.
          </AlertDescription>
        </Alert>
      ) : null}

      {scopedNoSourceSpend ? (
        <Alert>
          <AlertTitle>Нет рекламных расходов за период</AlertTitle>
          <AlertDescription>
            Источник рекламных расходов вернул 0 за выбранные даты.
          </AlertDescription>
        </Alert>
      ) : null}

      <ClusterEmptyNotice
        state={textOrNull(
          moneyK?.ad_cluster_state ??
            moneyData?.meta?.ad_cluster_state ??
            summary?.ad_cluster_state,
        )}
        rows={
          num(
            moneyK?.ad_cluster_rows ??
              moneyData?.meta?.ad_cluster_rows ??
              summary?.ad_cluster_rows,
          ) ?? 0
        }
      />

      {hasSpendReconciliationGap ? (
        <Alert className="border-info/30 bg-info/5">
          <WalletCards className="h-4 w-4 text-info" />
          <AlertTitle>Почему сумма отличается от панели владельца?</AlertTitle>
          <AlertDescription>
            В прибыли используется финальный расход из финансов WB:{" "}
            <span className="font-medium">{formatMoney(scopedFinalSpend)}</span>
            . В кабинете WB Ads за этот же период накоплено{" "}
            <span className="font-medium">
              {formatMoney(scopedSourceSpend)}
            </span>
            . Разница {formatMoney(Math.abs(spendReconciliationDiff))} возникает
            из-за разных источников и момента закрытия финансовых списаний.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricTile
          icon={WalletCards}
          label={hasScopedFilters ? "Расход по фильтру" : "Расход WB"}
          value={formatMoney(scopedSourceSpend)}
          sub={
            hasScopedFilters
              ? "По выбранным строкам WB Ads"
              : Math.abs(scopedFinalSpend - scopedSourceSpend) > 1
                ? `В прибыли: ${formatMoney(scopedFinalSpend)}`
                : undefined
          }
          accent="primary"
        />
        <MetricTile
          icon={Target}
          label={hasScopedFilters ? "ДРР по фильтру" : "ДРР WB"}
          value={scopedDrr != null ? formatPercent(scopedDrr) : "—"}
          sub={
            !hasScopedFilters &&
            scopedOwnerDrr != null &&
            scopedDrr != null &&
            Math.abs(scopedOwnerDrr - scopedDrr) > 0.1
              ? `В прибыли: ${formatPercent(scopedOwnerDrr)}`
              : undefined
          }
          tone={
            scopedDrr != null && scopedDrr >= 25
              ? "danger"
              : scopedDrr != null && scopedDrr >= 15
                ? "warning"
                : "success"
          }
        />
        <MetricTile
          icon={CircleDollarSign}
          label="Прибыль после рекламы"
          value={
            scopedProfitAfterAds == null
              ? "не рассчитано"
              : formatMoney(scopedProfitAfterAds)
          }
          tone={
            scopedProfitAfterAds != null && scopedProfitAfterAds < 0
              ? "danger"
              : "success"
          }
        />
        <MetricTile
          icon={BarChart3}
          label="Воронка"
          value={`${formatNumber(scopedClicks)} кликов`}
          sub={`${formatNumber(scopedViews)} показов, ${formatNumber(scopedAtbs)} корзин, CR ${
            scopedCr == null ? "—" : formatPercent(scopedCr)
          }`}
          tone="info"
        />
      </div>

      <div className="rounded-lg border bg-card p-4">
        <div className="grid gap-4 lg:grid-cols-[minmax(220px,360px)_1fr]">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
              <Layers3 className="h-3.5 w-3.5" />
              Разнос бюджета
            </div>
            <div className="flex items-end justify-between gap-3">
              <div>
                <div className="text-2xl font-semibold tabular-nums">
                  {formatPercent(scopedAllocationProgress, 0)}
                </div>
                <div className="text-xs text-muted-foreground">
                  {formatMoney(scopedAllocatedSpend)} из{" "}
                  {formatMoney(scopedSourceSpend)}
                </div>
              </div>
              <Badge
                variant="outline"
                className={toneClass(
                  scopedAllocationStatus === "overallocated"
                    ? "danger"
                    : scopedUnallocatedSpend > 0
                      ? "warning"
                      : "success",
                )}
              >
                {allocationStatusLabel(scopedAllocationStatus)}
              </Badge>
            </div>
            <Progress value={scopedAllocationProgress} className="mt-3 h-2" />
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            <MiniMetric
              label="Разнесено"
              value={formatMoney(scopedAllocatedSpend)}
            />
            <MiniMetric
              label="Не разнесено"
              value={formatMoney(scopedUnallocatedSpend)}
              tone={scopedUnallocatedSpend > 0 ? "warning" : "success"}
            />
            <MiniMetric
              label="Переаллокация"
              value={formatMoney(scopedOverallocatedSpend)}
              tone={scopedOverallocatedSpend > 0 ? "danger" : "success"}
            />
          </div>
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        <MiniMetric
          label="Заказы / товары"
          value={`${formatNumber(scopedOrders)} / ${formatNumber(scopedShks)}`}
        />
        <MiniMetric
          label="Корзины"
          value={formatNumber(scopedAtbs)}
          tone="info"
        />
        <MiniMetric
          label="Отмены"
          value={formatNumber(scopedCanceled)}
          tone={scopedCanceled > 0 ? "warning" : "success"}
        />
        <MiniMetric
          label="CPC WB"
          value={scopedCpc == null ? "—" : formatMoney(scopedCpc)}
        />
        <MiniMetric
          label="Доля затрат"
          value={
            scopedSpendShare == null ? "—" : formatPercent(scopedSpendShare)
          }
        />
      </div>

      <div className="rounded-lg border bg-card p-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
          <div className="relative min-w-[220px] flex-1 xl:max-w-sm">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="nm_id, SKU, advert_id, название"
              className="h-9 pl-9 text-sm"
            />
          </div>
          <div className="flex flex-wrap gap-1">
            {FILTERS.map(({ value, label, icon: Icon }) => (
              <Button
                key={value}
                size="sm"
                variant={rowFilter === value ? "default" : "outline"}
                className={cn(
                  "h-9 text-xs",
                  rowFilter === value && "bg-primary hover:bg-primary/90",
                )}
                onClick={() => setRowFilter(value)}
              >
                <Icon className="mr-1.5 h-3.5 w-3.5" />
                {label}
              </Button>
            ))}
          </div>
        </div>

        <div className="mt-3 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-wrap gap-1">
            {(
              [
                "all",
                "AD_PAUSE_REVIEW",
                "AD_SCALE_REVIEW",
                "AD_ALLOCATION_REVIEW",
                "DATA_FIX",
                "WATCH",
              ] as AdsHintFilter[]
            ).map((value) => {
              const Icon = value === "all" ? Eye : HINT_COPY[value].icon;
              const active = hintFilter === value;
              return (
                <Button
                  key={value}
                  size="sm"
                  variant={active ? "default" : "outline"}
                  className={cn(
                    "h-8 text-xs",
                    active &&
                      "bg-foreground text-background hover:bg-foreground/90",
                  )}
                  onClick={() => setHintFilter(value)}
                >
                  <Icon className="mr-1.5 h-3.5 w-3.5" />
                  {value === "all" ? "Все действия" : HINT_COPY[value].short}
                </Button>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-1">
            {SORTS.map(({ value, label, icon: Icon }) => (
              <Button
                key={value}
                size="sm"
                variant={sortMode === value ? "secondary" : "ghost"}
                className="h-8 text-xs"
                onClick={() => handleSort(value)}
              >
                <Icon className="mr-1.5 h-3.5 w-3.5" />
                {label}
                {sortMode === value ? (
                  <SortDirectionIcon
                    direction={sortDir}
                    className="ml-1 h-3.5 w-3.5"
                  />
                ) : null}
              </Button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-2">
        {filtered.length ? (
          <AdsRowsSortHeader
            sortMode={sortMode}
            sortDir={sortDir}
            onSort={handleSort}
          />
        ) : null}
        {filtered.map((row) => (
          <AdRowCard
            key={row.key}
            row={row}
            selected={selected?.key === row.key}
            onOpen={() => setSelected(row)}
          />
        ))}
        {!filtered.length ? (
          <div className="rounded-lg border border-dashed bg-card p-10 text-center">
            <PackageSearch className="mx-auto h-8 w-8 text-muted-foreground" />
            <div className="mt-3 font-medium">
              Нет строк по выбранным фильтрам
            </div>
            <div className="mt-1 text-sm text-muted-foreground">
              Попробуйте другой период или сбросьте фильтры.
            </div>
          </div>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card px-4 py-3 text-xs text-muted-foreground">
        <span>
          {hasScopedFilters
            ? `Показано ${formatNumber(filtered.length)} по фильтру из ${formatNumber(items.length)} загруженных строк.`
            : `Показано ${formatNumber(filtered.length)} из ${formatNumber(items.length)} на странице. Всего ${formatNumber(totalRows)}.`}
        </span>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={
              Boolean(productScopeNmId) || offset === 0 || eff.isFetching
            }
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Назад
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={
              Boolean(productScopeNmId) ||
              eff.isFetching ||
              items.length < efficiencyLimit
            }
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Вперёд
          </Button>
        </div>
      </div>

      <AdsDetailDrawer
        accountId={accountId}
        dateFrom={dateFrom}
        dateTo={dateTo}
        row={selected}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}

function AdsRowsSortHeader({
  sortMode,
  sortDir,
  onSort,
}: {
  sortMode: SortMode;
  sortDir: SortDirection;
  onSort: (value: SortMode) => void;
}) {
  return (
    <div className="rounded-lg border bg-card/80 p-3">
      <div className="grid gap-3 xl:grid-cols-[minmax(260px,1.2fr)_1.7fr_auto] xl:items-center">
        <div className="hidden min-w-0 text-[11px] font-medium uppercase text-muted-foreground xl:block">
          Карточка
        </div>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
          {ROW_SORT_HEADERS.map(({ value, label, icon: Icon }) => {
            const active = sortMode === value;
            return (
              <button
                key={value}
                type="button"
                onClick={() => onSort(value)}
                className={cn(
                  "flex h-9 min-w-0 items-center justify-between gap-1 rounded-md border px-2 text-left text-[11px] font-medium uppercase transition hover:border-primary/35 hover:bg-primary/5 focus:outline-none focus:ring-2 focus:ring-primary/25",
                  active
                    ? "border-primary/35 bg-primary/10 text-primary"
                    : "border-transparent bg-muted/50 text-muted-foreground",
                )}
                aria-label={`Сортировать по ${label}`}
              >
                <span className="flex min-w-0 items-center gap-1.5">
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{label}</span>
                </span>
                {active ? (
                  <SortDirectionIcon
                    direction={sortDir}
                    className="h-3.5 w-3.5 shrink-0"
                  />
                ) : (
                  <ArrowUpDown className="h-3.5 w-3.5 shrink-0 opacity-55" />
                )}
              </button>
            );
          })}
        </div>
        <div className="hidden text-right text-[11px] font-medium uppercase text-muted-foreground xl:block">
          Детали
        </div>
      </div>
    </div>
  );
}

function SortDirectionIcon({
  direction,
  className,
}: {
  direction: SortDirection;
  className?: string;
}) {
  const Icon = direction === "asc" ? ArrowUp : ArrowDown;
  return <Icon className={className} />;
}

function AdRowCard({
  row,
  selected,
  onOpen,
}: {
  row: EnrichedRow;
  selected: boolean;
  onOpen: () => void;
}) {
  const hint = HINT_COPY[row.hint];
  const Icon = hint.icon;
  const riskTone: Tone =
    row.profitAfterAds != null && row.profitAfterAds < 0
      ? "danger"
      : row.drr != null && row.drr >= 25
        ? "warning"
        : row.hint === "AD_SCALE_REVIEW"
          ? "success"
          : "default";

  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "group w-full rounded-lg border bg-card p-3 text-left transition hover:border-primary/40 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/30",
        selected && "border-primary/50 ring-2 ring-primary/15",
      )}
    >
      <div className="grid gap-3 xl:grid-cols-[minmax(260px,1.2fr)_1.7fr_auto] xl:items-center">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            <GranularityBadge row={row.raw} />
            <AllocationStatusBadge status={row.allocationStatus} />
            <Badge variant="outline" className={toneClass(hint.tone)}>
              <Icon className="mr-1 h-3 w-3" />
              {hint.short}
            </Badge>
          </div>
          <div className="truncate text-sm font-semibold">{row.title}</div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>nm {row.nmId ?? "—"}</span>
            <span>SKU {row.skuId ?? "—"}</span>
            <span>{row.vendorCode ?? "без артикула"}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
          <InlineMetric
            label="Затраты WB"
            value={formatMoney(row.sourceAdSpend || row.adSpend)}
          />
          <InlineMetric
            label="ДРР"
            value={row.drr != null ? formatPercent(row.drr) : "—"}
            tone={
              row.drr != null && row.drr >= 25
                ? "danger"
                : row.drr != null && row.drr >= 15
                  ? "warning"
                  : "success"
            }
          />
          <InlineMetric
            label="Прибыль"
            value={
              row.profitAfterAds == null ? "—" : formatMoney(row.profitAfterAds)
            }
            tone={riskTone}
          />
          <InlineMetric label="Клики" value={formatNumber(row.clicks)} />
          <InlineMetric
            label="CR"
            value={row.cr == null ? "—" : formatPercent(row.cr)}
            tone={
              row.cr != null && row.cr >= 2
                ? "success"
                : row.cr != null && row.cr > 0
                  ? "warning"
                  : "default"
            }
          />
          <InlineMetric
            label="Заказы / товары"
            value={`${formatNumber(row.orders)} / ${formatNumber(row.shks)}`}
          />
          <InlineMetric
            label="Отмены"
            value={formatNumber(row.canceled)}
            tone={row.canceled > 0 ? "warning" : "success"}
          />
          <InlineMetric
            label="Доля затрат"
            value={row.spendShare == null ? "—" : formatPercent(row.spendShare)}
          />
        </div>

        <div className="flex items-center justify-between gap-3 xl:justify-end">
          <div className="min-w-0 text-xs text-muted-foreground xl:max-w-[220px]">
            <div className="truncate font-medium text-foreground">
              {row.campaignName}
            </div>
            <div className="truncate">
              {row.advertId
                ? `advert ${row.advertId}`
                : row.advertIds.length
                  ? `${row.advertIds.length} кампаний`
                  : "без campaign id"}
            </div>
          </div>
          <ChevronRight className="h-5 w-5 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" />
        </div>
      </div>
    </button>
  );
}

function AdsDetailDrawer({
  accountId,
  dateFrom,
  dateTo,
  row,
  onClose,
}: {
  accountId: number;
  dateFrom: string;
  dateTo: string;
  row: EnrichedRow | null;
  onClose: () => void;
}) {
  const [tab, setTab] = useState("overview");
  const open = Boolean(row);
  const advertIds = useMemo(
    () => (row ? row.advertIds.slice(0, 8) : []),
    [row],
  );

  useEffect(() => {
    if (open) setTab("overview");
  }, [open, row?.key]);

  const statsQ = useQuery({
    queryKey: [
      "ads-detail-stats",
      accountId,
      row?.nmId,
      row?.advertId,
      dateFrom,
      dateTo,
    ],
    queryFn: ({ signal }) =>
      api<ApiPage<AdStat> | AdStat[]>(API_ENDPOINTS.ads.stats, {
        query: {
          account_id: accountId,
          nm_id: row?.nmId ?? undefined,
          advert_id: row?.advertId ?? undefined,
          date_from: dateFrom,
          date_to: dateTo,
          sort_by: "stat_date",
          sort_dir: "desc",
          limit: 120,
        },
        signal,
      }),
    enabled: open && row?.nmId != null,
    staleTime: 60_000,
  });

  const clustersQ = useQuery({
    queryKey: [
      "ads-detail-clusters",
      accountId,
      row?.nmId,
      row?.advertId,
      dateFrom,
      dateTo,
    ],
    queryFn: ({ signal }) =>
      api<ApiPage<AdCluster> | AdCluster[]>(API_ENDPOINTS.ads.clusters, {
        query: {
          account_id: accountId,
          nm_id: row?.nmId ?? undefined,
          advert_id: row?.advertId ?? undefined,
          date_from: dateFrom,
          date_to: dateTo,
          sort_by: "spend",
          sort_dir: "desc",
          limit: 80,
        },
        signal,
      }),
    enabled: open && row?.nmId != null,
    staleTime: 60_000,
  });

  const campaignQueries = useQueries({
    queries: advertIds.map((advertId) => ({
      queryKey: ["ads-campaign-detail", accountId, advertId],
      queryFn: ({ signal }: { signal?: AbortSignal }) =>
        api<AdCampaign>(API_ENDPOINTS.ads.campaignDetail(advertId), {
          query: { account_id: accountId },
          signal,
        }),
      enabled: open,
      staleTime: 60_000,
    })),
  });

  const stats = pageItems<AdStat>(statsQ.data);
  const clusters = pageItems<AdCluster>(clustersQ.data);
  const campaigns = campaignQueries
    .map((query) => query.data)
    .filter(Boolean) as AdCampaign[];
  const loadingDetail =
    statsQ.isFetching ||
    clustersQ.isFetching ||
    campaignQueries.some((query) => query.isFetching);

  return (
    <Sheet open={open} onOpenChange={(value) => !value && onClose()}>
      <SheetContent
        side="right"
        className="flex w-full flex-col overflow-hidden p-0 sm:max-w-5xl"
      >
        {row ? (
          <>
            <SheetHeader className="border-b px-6 pb-4 pt-6 pr-12">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge
                      variant="outline"
                      className="border-primary/30 bg-primary/5 text-primary"
                    >
                      WB Ads
                    </Badge>
                    <GranularityBadge row={row.raw} />
                    <AllocationStatusBadge status={row.allocationStatus} />
                  </div>
                  <SheetTitle className="truncate text-xl">
                    {row.title}
                  </SheetTitle>
                  <SheetDescription className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                    <span>nm {row.nmId ?? "—"}</span>
                    <span>SKU {row.skuId ?? "—"}</span>
                    <span>{row.campaignName}</span>
                  </SheetDescription>
                </div>
                <div className="flex flex-wrap gap-2">
                  {row.nmId ? (
                    <Button asChild size="sm" variant="outline">
                      <Link
                        to="/products/$nmId"
                        params={{ nmId: String(row.nmId) }}
                      >
                        Карточка
                        <ArrowRight className="ml-2 h-3.5 w-3.5" />
                      </Link>
                    </Button>
                  ) : null}
                  <Button asChild size="sm" variant="outline">
                    <Link to="/data-fix">
                      <Wrench className="mr-2 h-3.5 w-3.5" />
                      Данные
                    </Link>
                  </Button>
                </div>
              </div>
            </SheetHeader>

            <div className="grid gap-2 border-b bg-muted/30 px-6 py-3 sm:grid-cols-2 xl:grid-cols-6">
              <MiniMetric
                label="Затраты WB"
                value={formatMoney(row.sourceAdSpend || row.adSpend)}
              />
              <MiniMetric
                label="Рекл. выручка"
                value={formatMoney(row.adRevenue || row.revenue)}
              />
              <MiniMetric
                label="ДРР"
                value={row.drr != null ? formatPercent(row.drr) : "—"}
                tone={row.drr != null && row.drr >= 25 ? "danger" : "success"}
              />
              <MiniMetric
                label="Прибыль"
                value={
                  row.profitAfterAds == null
                    ? "—"
                    : formatMoney(row.profitAfterAds)
                }
                tone={
                  row.profitAfterAds != null && row.profitAfterAds < 0
                    ? "danger"
                    : "success"
                }
              />
              <MiniMetric
                label="Клики / заказы"
                value={`${formatNumber(row.clicks)} / ${formatNumber(row.orders)}`}
              />
              <MiniMetric
                label="CR / отмены"
                value={`${row.cr == null ? "—" : formatPercent(row.cr)} / ${formatNumber(row.canceled)}`}
                tone={row.canceled > 0 ? "warning" : "default"}
              />
            </div>

            <Tabs
              value={tab}
              onValueChange={setTab}
              className="flex min-h-0 flex-1 flex-col"
            >
              <div className="border-b px-6 py-3">
                <TabsList className="h-auto flex-wrap">
                  <TabsTrigger value="overview" className="text-xs">
                    Сводка
                  </TabsTrigger>
                  <TabsTrigger value="trends" className="text-xs">
                    Динамика
                  </TabsTrigger>
                  <TabsTrigger value="days" className="text-xs">
                    Дни
                  </TabsTrigger>
                  <TabsTrigger value="clusters" className="text-xs">
                    Кластеры
                  </TabsTrigger>
                  <TabsTrigger value="campaigns" className="text-xs">
                    Кампании
                  </TabsTrigger>
                </TabsList>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6">
                <TabsContent value="overview" className="mt-4 space-y-4">
                  <DetailOverview row={row} />
                </TabsContent>

                <TabsContent value="trends" className="mt-4 space-y-4">
                  <DetailLoading show={statsQ.isFetching} />
                  <AdsTrendPanel row={row} stats={stats} />
                </TabsContent>

                <TabsContent value="days" className="mt-4 space-y-3">
                  <DetailLoading show={statsQ.isFetching} />
                  {stats.map((stat) => (
                    <DailyStatRow key={stat.id} stat={stat} />
                  ))}
                  {!stats.length && !statsQ.isFetching ? (
                    <EmptyPanel
                      icon={CalendarDays}
                      text="Нет дневной статистики за период"
                    />
                  ) : null}
                </TabsContent>

                <TabsContent value="clusters" className="mt-4 space-y-3">
                  <DetailLoading show={clustersQ.isFetching} />
                  <ClusterVisualSummary clusters={clusters} />
                  {clusters.map((cluster) => (
                    <ClusterRow
                      key={cluster.id}
                      cluster={cluster}
                      maxSpend={Math.max(
                        ...clusters.map((item) => num(item.sum) ?? 0),
                        1,
                      )}
                    />
                  ))}
                  {!clusters.length && !clustersQ.isFetching ? (
                    <EmptyPanel
                      icon={LineChart}
                      text="Нет сохранённых поисковых кластеров"
                    />
                  ) : null}
                </TabsContent>

                <TabsContent value="campaigns" className="mt-4 space-y-3">
                  <DetailLoading show={loadingDetail} />
                  {campaigns.map((campaign) => (
                    <CampaignPanel
                      key={campaign.advert_id}
                      campaign={campaign}
                    />
                  ))}
                  {!campaigns.length && !loadingDetail ? (
                    <EmptyPanel
                      icon={Target}
                      text="Кампании не найдены в локальном хранилище"
                    />
                  ) : null}
                </TabsContent>
              </div>
            </Tabs>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function DetailOverview({ row }: { row: EnrichedRow }) {
  const hint = HINT_COPY[row.hint];
  const Icon = hint.icon;
  const allocationProgress =
    row.sourceAdSpend > 0
      ? clamp((row.adSpend / row.sourceAdSpend) * 100, 0, 100)
      : 0;

  return (
    <>
      <div className="rounded-lg border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Решение</div>
            <div className="mt-1 text-sm text-muted-foreground">
              {hint.label}
            </div>
          </div>
          <Badge variant="outline" className={toneClass(hint.tone)}>
            <Icon className="mr-1.5 h-3.5 w-3.5" />
            {hint.short}
          </Badge>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-lg border bg-card p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold">Экономика</div>
            <Badge variant="outline">
              {row.confidence === "high"
                ? "высокая точность"
                : row.confidence || "—"}
            </Badge>
          </div>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Fact
              label="Затраты WB"
              value={formatMoney(row.sourceAdSpend || row.adSpend)}
            />
            <Fact label="Расход в прибыли" value={formatMoney(row.adSpend)} />
            <Fact label="Raw расход" value={formatMoney(row.rawAdSpend)} />
            <Fact
              label="Рекламная выручка WB"
              value={formatMoney(row.adRevenue || row.revenue)}
            />
            <Fact
              label="Бизнес выручка"
              value={formatMoney(row.businessRevenue)}
            />
            <Fact
              label="Прибыль после рекламы"
              value={
                row.profitAfterAds == null
                  ? "—"
                  : formatMoney(row.profitAfterAds)
              }
            />
            <Fact
              label="ДРР"
              value={row.drr == null ? "—" : formatPercent(row.drr)}
            />
            <Fact
              label="CPC"
              value={row.cpc == null ? "—" : formatMoney(row.cpc)}
            />
            <Fact
              label="Доля затрат"
              value={
                row.spendShare == null ? "—" : formatPercent(row.spendShare)
              }
            />
          </dl>
        </div>

        <div className="rounded-lg border bg-card p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold">Разнос</div>
            <AllocationStatusBadge status={row.allocationStatus} />
          </div>
          <Progress value={allocationProgress} className="h-2" />
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <Fact label="Источник" value={formatMoney(row.sourceAdSpend)} />
            <Fact label="Разнесено" value={formatMoney(row.adSpend)} />
            <Fact
              label="Не разнесено"
              value={formatMoney(row.unallocatedAdSpend)}
            />
            <Fact
              label="Переаллокация"
              value={formatMoney(row.overallocatedAdSpend)}
            />
          </dl>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <MiniMetric label="Показы" value={formatNumber(row.views)} />
        <MiniMetric
          label="CTR"
          value={row.ctr == null ? "—" : formatPercent(row.ctr)}
        />
        <MiniMetric
          label="CR"
          value={row.cr == null ? "—" : formatPercent(row.cr)}
        />
        <MiniMetric
          label="Корзины"
          value={formatNumber(row.atbs)}
          tone="info"
        />
        <MiniMetric
          label="Заказы / товары"
          value={`${formatNumber(row.orders)} / ${formatNumber(row.shks)}`}
        />
        <MiniMetric
          label="Отмены"
          value={formatNumber(row.canceled)}
          tone={row.canceled > 0 ? "warning" : "success"}
        />
      </div>

      {row.blockedReasons.length ? (
        <div className="rounded-lg border border-warning/30 bg-warning/5 p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-warning">
            <Wrench className="h-4 w-4" />
            Блокирующие данные
          </div>
          <div className="flex flex-wrap gap-2">
            {row.blockedReasons.map((reason) => (
              <Badge
                key={reason}
                variant="outline"
                className="border-warning/30 bg-card text-warning"
              >
                {reason}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}

function AdsTrendPanel({ row, stats }: { row: EnrichedRow; stats: AdStat[] }) {
  const trend = useMemo(() => buildAdsTrend(stats), [stats]);
  const comparison = useMemo(() => compareTrendWindows(trend), [trend]);

  if (!trend.length) {
    return (
      <EmptyPanel
        icon={LineChart}
        text="Для этой строки пока нет дневной динамики"
      />
    );
  }

  const chartData = trend.slice(-45);
  const latest = trend[trend.length - 1];
  const spendTone = trendTone(comparison.spendChange, false);
  const ordersTone = trendTone(comparison.ordersChange, true);
  const drrTone = trendTone(comparison.drrChange, false);

  return (
    <>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <TrendSignalCard
          icon={WalletCards}
          label="Расход"
          value={formatMoney(comparison.recentSpend)}
          change={comparison.spendChange}
          tone={spendTone}
          sub={`${comparison.recentDays} дн. к предыдущим ${comparison.previousDays || comparison.recentDays}`}
        />
        <TrendSignalCard
          icon={Target}
          label="DRR"
          value={
            comparison.recentDrr == null
              ? "—"
              : formatPercent(comparison.recentDrr)
          }
          change={comparison.drrChange}
          tone={drrTone}
          inverse
          sub="ниже лучше"
        />
        <TrendSignalCard
          icon={BarChart3}
          label="Заказы"
          value={formatNumber(comparison.recentOrders)}
          change={comparison.ordersChange}
          tone={ordersTone}
          sub={`${formatNumber(latest.clicks)} кликов в последний день`}
        />
        <TrendSignalCard
          icon={TrendingUp}
          label="Прогноз 7 дн."
          value={formatMoney(comparison.forecastSpend7d)}
          tone={
            comparison.forecastDrr7d != null && comparison.forecastDrr7d >= 25
              ? "warning"
              : "success"
          }
          sub={`${formatNumber(comparison.forecastOrders7d)} заказов · ${
            comparison.forecastDrr7d == null
              ? "DRR —"
              : formatPercent(comparison.forecastDrr7d)
          }`}
        />
      </div>

      <div className="rounded-lg border bg-card p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold">
              <LineChart className="h-4 w-4 text-primary" />
              Динамика расхода и заказов
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {formatDate(trend[0].date)} - {formatDate(latest.date)}
            </div>
          </div>
          <Badge variant="outline" className="bg-muted/40">
            {trend.length} дн.
          </Badge>
        </div>

        <div className="h-[320px] min-h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={chartData}
              margin={{ top: 14, right: 12, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="date"
                tickFormatter={shortDate}
                tickLine={false}
                axisLine={false}
                minTickGap={20}
              />
              <YAxis
                yAxisId="orders"
                tickLine={false}
                axisLine={false}
                width={42}
              />
              <YAxis
                yAxisId="money"
                orientation="right"
                tickFormatter={(value) => formatMoneyCompact(Number(value))}
                tickLine={false}
                axisLine={false}
                width={62}
              />
              <RechartsTooltip content={<AdsTrendTooltip />} />
              <Bar
                yAxisId="money"
                dataKey="revenue"
                name="Выручка"
                fill="var(--success)"
                fillOpacity={0.18}
                radius={[3, 3, 0, 0]}
              />
              <Bar
                yAxisId="money"
                dataKey="spend"
                name="Расход"
                fill="var(--primary)"
                fillOpacity={0.82}
                radius={[3, 3, 0, 0]}
              />
              <Line
                yAxisId="orders"
                type="monotone"
                dataKey="orders"
                name="Заказы"
                stroke="var(--success)"
                strokeWidth={2}
                dot={false}
              />
              <Line
                yAxisId="orders"
                type="monotone"
                dataKey="atbs"
                name="Корзины"
                stroke="var(--info)"
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MiniMetric
          label="Последний день"
          value={`${formatMoney(latest.spend)} · ${formatNumber(latest.orders)} зак.`}
        />
        <MiniMetric
          label="CTR / CR"
          value={`${latest.ctr == null ? "—" : formatPercent(latest.ctr)} / ${
            latest.cr == null ? "—" : formatPercent(latest.cr)
          }`}
        />
        <MiniMetric
          label="Товары / отмены"
          value={`${formatNumber(latest.shks)} / ${formatNumber(latest.canceled)}`}
          tone={latest.canceled > 0 ? "warning" : "default"}
        />
        <MiniMetric
          label="CPC"
          value={latest.cpc == null ? "—" : formatMoney(latest.cpc)}
        />
        <MiniMetric
          label="Сигнал"
          value={trendSignalLabel({
            spendChange: comparison.spendChange,
            ordersChange: comparison.ordersChange,
            drrChange: comparison.drrChange,
            profit: row.profitAfterAds,
          })}
          tone={
            row.profitAfterAds != null && row.profitAfterAds < 0
              ? "danger"
              : ordersTone
          }
        />
      </div>
    </>
  );
}

function TrendSignalCard({
  icon: Icon,
  label,
  value,
  change,
  tone = "default",
  sub,
  inverse = false,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  change?: number | null;
  tone?: Tone;
  sub?: string;
  inverse?: boolean;
}) {
  const normalizedChange = change == null ? null : inverse ? -change : change;
  const ChangeIcon =
    normalizedChange == null || Math.abs(normalizedChange) < 1
      ? LineChart
      : normalizedChange > 0
        ? TrendingUp
        : TrendingDown;

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-xs font-medium uppercase text-muted-foreground">
          {label}
        </div>
        <div
          className={cn(
            "grid h-8 w-8 place-items-center rounded-md",
            toneIconClass(tone),
          )}
        >
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div
        className={cn(
          "text-xl font-semibold tabular-nums",
          valueToneClass(tone),
        )}
      >
        {value}
      </div>
      <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
        <ChangeIcon className={cn("h-3.5 w-3.5", valueToneClass(tone))} />
        <span>
          {change == null ? "нет сравнения" : formatSignedPercent(change)}
        </span>
      </div>
      {sub ? (
        <div className="mt-1 text-xs text-muted-foreground">{sub}</div>
      ) : null}
    </div>
  );
}

function AdsTrendTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload?: AdsTrendPoint }>;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  if (!point) return null;
  return (
    <div className="rounded-md border bg-popover p-3 text-xs shadow-md">
      <div className="mb-2 font-semibold">{formatDate(point.date)}</div>
      <div className="grid gap-1">
        <TooltipRow label="Расход" value={formatMoney(point.spend)} />
        <TooltipRow label="Выручка" value={formatMoney(point.revenue)} />
        <TooltipRow
          label="DRR"
          value={point.drr == null ? "—" : formatPercent(point.drr)}
        />
        <TooltipRow
          label="CR"
          value={point.cr == null ? "—" : formatPercent(point.cr)}
        />
        <TooltipRow label="Показы" value={formatNumber(point.views)} />
        <TooltipRow label="Клики" value={formatNumber(point.clicks)} />
        <TooltipRow label="Корзины" value={formatNumber(point.atbs)} />
        <TooltipRow label="Заказы" value={formatNumber(point.orders)} />
        <TooltipRow label="Товары" value={formatNumber(point.shks)} />
        <TooltipRow label="Отмены" value={formatNumber(point.canceled)} />
      </div>
    </div>
  );
}

function TooltipRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-[180px] items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  );
}

function ClusterVisualSummary({ clusters }: { clusters: AdCluster[] }) {
  const rows = useMemo(
    () => aggregateClusters(clusters).slice(0, 8),
    [clusters],
  );
  const maxSpend = Math.max(...rows.map((item) => item.spend), 1);

  if (!rows.length) return null;

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <PackageSearch className="h-4 w-4 text-primary" />
          Топ поисковых кластеров
        </div>
        <Badge variant="outline" className="bg-muted/40">
          {rows.length} из {clusters.length}
        </Badge>
      </div>
      <div className="grid gap-3">
        {rows.map((item, index) => {
          const share = clamp((item.spend / maxSpend) * 100, 5, 100);
          return (
            <div
              key={item.key}
              className="grid gap-2 sm:grid-cols-[minmax(160px,1fr)_2fr_auto] sm:items-center"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">
                  {index + 1}. {item.key}
                </div>
                <div className="text-xs text-muted-foreground">
                  {formatNumber(item.clicks)} кликов ·{" "}
                  {formatNumber(item.orders)} заказов ·{" "}
                  {formatNumber(item.shks)} товаров
                </div>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${share}%` }}
                />
              </div>
              <div className="text-right text-sm font-semibold tabular-nums">
                {formatMoney(item.spend)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DailyStatRow({ stat }: { stat: AdStat }) {
  const spend = num(stat.sum) ?? 0;
  const views = num(stat.views) ?? 0;
  const clicks = num(stat.clicks) ?? 0;
  const orders = num(stat.orders) ?? 0;
  const shks = num(stat.shks) ?? 0;
  const canceled = num(stat.canceled) ?? 0;
  const cr =
    num(stat.cr) ?? (clicks > 0 && orders > 0 ? (orders / clicks) * 100 : null);
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">
            {formatDate(stat.stat_date)}
          </div>
          <div className="text-xs text-muted-foreground">
            advert {stat.advert_id}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8">
          <InlineMetric label="Расход" value={formatMoney(spend)} />
          <InlineMetric label="Показы" value={formatNumber(views)} />
          <InlineMetric label="Клики" value={formatNumber(clicks)} />
          <InlineMetric
            label="CTR"
            value={stat.ctr == null ? "—" : formatPercent(Number(stat.ctr))}
          />
          <InlineMetric
            label="CPC"
            value={stat.cpc == null ? "—" : formatMoney(Number(stat.cpc))}
          />
          <InlineMetric
            label="CR"
            value={cr == null ? "—" : formatPercent(cr)}
          />
          <InlineMetric
            label="Заказы / товары"
            value={`${formatNumber(orders)} / ${formatNumber(shks)}`}
          />
          <InlineMetric
            label="Отмены"
            value={formatNumber(canceled)}
            tone={canceled > 0 ? "warning" : "success"}
          />
        </div>
      </div>
    </div>
  );
}

function ClusterRow({
  cluster,
  maxSpend,
}: {
  cluster: AdCluster;
  maxSpend: number;
}) {
  const spend = num(cluster.sum) ?? 0;
  const share = maxSpend > 0 ? clamp((spend / maxSpend) * 100, 4, 100) : 0;
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-[220px] flex-1">
          <div className="truncate text-sm font-semibold">
            {cluster.cluster || "Без названия"}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {formatDate(cluster.stat_date)} · advert {cluster.advert_id}
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${share}%` }}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
          <InlineMetric label="Расход" value={formatMoney(spend)} />
          <InlineMetric
            label="Показы"
            value={formatNumber(cluster.views ?? 0)}
          />
          <InlineMetric
            label="Клики"
            value={formatNumber(cluster.clicks ?? 0)}
          />
          <InlineMetric
            label="Позиция"
            value={
              cluster.avg_position == null
                ? "—"
                : Number(cluster.avg_position).toFixed(1)
            }
          />
          <InlineMetric
            label="Заказы"
            value={formatNumber(cluster.orders ?? 0)}
          />
          <InlineMetric
            label="Товары"
            value={formatNumber(cluster.shks ?? 0)}
          />
        </div>
      </div>
    </div>
  );
}

function CampaignPanel({ campaign }: { campaign: AdCampaign }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">
            {campaign.name || `Кампания ${campaign.advert_id}`}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>advert {campaign.advert_id}</span>
            <span>{campaignTypeLabel(campaign.campaign_type)}</span>
            <span>{formatDateTime(campaign.change_time)}</span>
          </div>
        </div>
        <Badge
          variant="outline"
          className={campaignStatusTone(campaign.status)}
        >
          {campaignStatusLabel(campaign.status)}
        </Badge>
      </div>

      {campaign.items?.length ? (
        <div className="mt-4">
          <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">
            Карточки внутри кампании
          </div>
          <div className="flex flex-wrap gap-2">
            {campaign.items.slice(0, 40).map((item) => (
              <Badge key={item.id} variant="outline" className="bg-muted/40">
                {item.nm_id ?? "—"} {item.name ? `· ${item.name}` : ""}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}

      <details className="mt-4 rounded-md border bg-muted/30 p-3">
        <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
          WB payload
        </summary>
        <JsonPreview value={campaign.payload ?? {}} />
      </details>
    </div>
  );
}

function MetricTile({
  icon: Icon,
  label,
  value,
  sub,
  tone = "default",
  accent,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
  accent?: "primary";
}) {
  return (
    <Card className="overflow-hidden">
      {accent === "primary" ? <div className="h-1 bg-primary" /> : null}
      <CardContent className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-xs font-medium uppercase text-muted-foreground">
            {label}
          </div>
          <div
            className={cn(
              "grid h-8 w-8 place-items-center rounded-md",
              accent === "primary"
                ? "bg-primary/10 text-primary"
                : toneIconClass(tone),
            )}
          >
            <Icon className="h-4 w-4" />
          </div>
        </div>
        <div
          className={cn(
            "text-2xl font-semibold tabular-nums",
            valueToneClass(tone),
          )}
        >
          {value}
        </div>
        {sub ? (
          <div className="mt-1 text-xs text-muted-foreground">{sub}</div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function MiniMetric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: Tone;
}) {
  return (
    <div className="rounded-md border bg-background/60 p-3">
      <div className="text-[11px] font-medium uppercase text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 text-base font-semibold tabular-nums",
          valueToneClass(tone),
        )}
      >
        {value}
      </div>
    </div>
  );
}

function InlineMetric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: Tone;
}) {
  return (
    <div className="min-w-0 rounded-md bg-muted/50 px-2.5 py-2">
      <div className="truncate text-[10px] uppercase text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "truncate text-sm font-semibold tabular-nums",
          valueToneClass(tone),
        )}
      >
        {value}
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-medium tabular-nums">{value}</dd>
    </div>
  );
}

function DetailLoading({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="flex items-center gap-2 rounded-lg border bg-card p-3 text-sm text-muted-foreground">
      <RefreshCw className="h-4 w-4 animate-spin" />
      Загрузка детализации
    </div>
  );
}

function EmptyPanel({
  icon: Icon,
  text,
}: {
  icon: ComponentType<{ className?: string }>;
  text: string;
}) {
  return (
    <div className="rounded-lg border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">
      <Icon className="mx-auto mb-2 h-7 w-7" />
      {text}
    </div>
  );
}

function JsonPreview({ value }: { value: unknown }) {
  return (
    <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-background p-3 text-[11px] leading-relaxed text-muted-foreground">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  );
}

function buildAdsTrend(stats: AdStat[]): AdsTrendPoint[] {
  const byDate = new Map<string, AdsTrendPoint>();

  for (const stat of stats) {
    const date = String(stat.stat_date || "").slice(0, 10);
    if (!date) continue;
    const point = byDate.get(date) ?? {
      date,
      label: shortDate(date),
      spend: 0,
      revenue: 0,
      views: 0,
      clicks: 0,
      orders: 0,
      shks: 0,
      atbs: 0,
      canceled: 0,
      drr: null,
      ctr: null,
      cr: null,
      cpc: null,
    };
    point.spend += num(stat.sum) ?? 0;
    point.revenue += num(stat.sum_price) ?? 0;
    point.views += num(stat.views) ?? 0;
    point.clicks += num(stat.clicks) ?? 0;
    point.orders += num(stat.orders) ?? 0;
    point.shks += num(stat.shks) ?? 0;
    point.atbs += num(stat.atbs) ?? 0;
    point.canceled += num(stat.canceled) ?? 0;
    byDate.set(date, point);
  }

  return [...byDate.values()]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((point) => ({
      ...point,
      drr:
        point.revenue > 0 && point.spend > 0
          ? (point.spend / point.revenue) * 100
          : null,
      ctr:
        point.views > 0 && point.clicks > 0
          ? (point.clicks / point.views) * 100
          : null,
      cr:
        point.clicks > 0 && point.orders > 0
          ? (point.orders / point.clicks) * 100
          : null,
      cpc:
        point.clicks > 0 && point.spend > 0 ? point.spend / point.clicks : null,
    }));
}

function compareTrendWindows(points: AdsTrendPoint[]): TrendComparison {
  if (!points.length) {
    return {
      recentDays: 0,
      previousDays: 0,
      spendChange: null,
      ordersChange: null,
      drrChange: null,
      recentSpend: 0,
      recentRevenue: 0,
      recentOrders: 0,
      recentDrr: null,
      forecastSpend7d: 0,
      forecastRevenue7d: 0,
      forecastOrders7d: 0,
      forecastDrr7d: null,
    };
  }

  const windowSize = Math.max(
    1,
    Math.min(7, Math.floor(points.length / 2) || 1),
  );
  const recent = points.slice(-windowSize);
  let previous = points.slice(
    Math.max(0, points.length - windowSize * 2),
    points.length - windowSize,
  );
  if (!previous.length && points.length > 1) {
    const midpoint = Math.floor(points.length / 2);
    previous = points.slice(0, midpoint);
  }

  const recentTotals = trendTotals(recent);
  const previousTotals = trendTotals(previous);
  const recentDrr = ratioPercent(recentTotals.spend, recentTotals.revenue);
  const previousDrr = ratioPercent(
    previousTotals.spend,
    previousTotals.revenue,
  );
  const forecastSpend7d = forecast7d(
    recentTotals.spend,
    previousTotals.spend,
    recent.length,
    previous.length,
  );
  const forecastRevenue7d = forecast7d(
    recentTotals.revenue,
    previousTotals.revenue,
    recent.length,
    previous.length,
  );
  const forecastOrders7d = Math.round(
    forecast7d(
      recentTotals.orders,
      previousTotals.orders,
      recent.length,
      previous.length,
    ),
  );

  return {
    recentDays: recent.length,
    previousDays: previous.length,
    spendChange: percentChange(recentTotals.spend, previousTotals.spend),
    ordersChange: percentChange(recentTotals.orders, previousTotals.orders),
    drrChange:
      recentDrr == null || previousDrr == null
        ? null
        : percentChange(recentDrr, previousDrr),
    recentSpend: recentTotals.spend,
    recentRevenue: recentTotals.revenue,
    recentOrders: recentTotals.orders,
    recentDrr,
    forecastSpend7d,
    forecastRevenue7d,
    forecastOrders7d,
    forecastDrr7d: ratioPercent(forecastSpend7d, forecastRevenue7d),
  };
}

function trendTotals(points: AdsTrendPoint[]) {
  return points.reduce(
    (total, point) => ({
      spend: total.spend + point.spend,
      revenue: total.revenue + point.revenue,
      orders: total.orders + point.orders,
    }),
    { spend: 0, revenue: 0, orders: 0 },
  );
}

function forecast7d(
  recentTotal: number,
  previousTotal: number,
  recentDays: number,
  previousDays: number,
): number {
  if (recentDays <= 0) return 0;
  const recentAvg = recentTotal / recentDays;
  if (previousDays <= 0) return Math.max(0, recentAvg * 7);
  const previousAvg = previousTotal / previousDays;
  const projectedDaily = recentAvg + (recentAvg - previousAvg) * 0.35;
  return Math.max(0, projectedDaily * 7);
}

function percentChange(current: number, previous: number): number | null {
  if (
    !Number.isFinite(current) ||
    !Number.isFinite(previous) ||
    previous <= 0
  ) {
    return null;
  }
  return ((current - previous) / previous) * 100;
}

function ratioPercent(part: number, total: number): number | null {
  return total > 0 ? (part / total) * 100 : null;
}

function trendTone(change: number | null, positiveBetter: boolean): Tone {
  if (change == null || Math.abs(change) < 5) return "default";
  if (positiveBetter) return change > 0 ? "success" : "danger";
  return change > 0 ? "warning" : "success";
}

function trendSignalLabel({
  spendChange,
  ordersChange,
  drrChange,
  profit,
}: {
  spendChange: number | null;
  ordersChange: number | null;
  drrChange: number | null;
  profit: number | null;
}): string {
  if (profit != null && profit < 0) return "Убыток: проверить ставку";
  if ((drrChange ?? 0) > 10 && (ordersChange ?? 0) <= 0) {
    return "DRR растёт без роста заказов";
  }
  if ((spendChange ?? 0) > 10 && (ordersChange ?? 0) < 5) {
    return "Расход растёт быстрее заказов";
  }
  if ((ordersChange ?? 0) > 10 && (drrChange ?? 0) < 5) {
    return "Рост с контролем DRR";
  }
  if ((spendChange ?? 0) < -10 && (ordersChange ?? 0) < -10) {
    return "Трафик проседает";
  }
  return "Стабильно";
}

function aggregateClusters(clusters: AdCluster[]): ClusterAggregate[] {
  const map = new Map<
    string,
    ClusterAggregate & { positionWeight: number; positionTotal: number }
  >();

  for (const cluster of clusters) {
    const key = String(cluster.cluster || "Без названия");
    const spend = num(cluster.sum) ?? 0;
    const position = num(cluster.avg_position);
    const row = map.get(key) ?? {
      key,
      spend: 0,
      views: 0,
      clicks: 0,
      orders: 0,
      shks: 0,
      avgPosition: null,
      positionWeight: 0,
      positionTotal: 0,
    };
    row.spend += spend;
    row.views += num(cluster.views) ?? 0;
    row.clicks += num(cluster.clicks) ?? 0;
    row.orders += num(cluster.orders) ?? 0;
    row.shks += num(cluster.shks) ?? 0;
    if (position != null) {
      const weight = Math.max(spend, 1);
      row.positionWeight += weight;
      row.positionTotal += position * weight;
    }
    map.set(key, row);
  }

  return [...map.values()]
    .map((row) => ({
      key: row.key,
      spend: row.spend,
      views: row.views,
      clicks: row.clicks,
      orders: row.orders,
      shks: row.shks,
      avgPosition:
        row.positionWeight > 0 ? row.positionTotal / row.positionWeight : null,
    }))
    .sort((a, b) => b.spend - a.spend);
}

function shortDate(value: string): string {
  const date = String(value || "").slice(0, 10);
  const parts = date.split("-");
  if (parts.length === 3) return `${parts[2]}.${parts[1]}`;
  return date || "—";
}

function formatSignedPercent(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${formatPercent(Math.abs(value))}`;
}

function compareAdsRows(
  a: EnrichedRow,
  b: EnrichedRow,
  sortMode: SortMode,
  sortDir: SortDirection,
): number {
  const av = adsSortValue(a, sortMode);
  const bv = adsSortValue(b, sortMode);
  const aMissing = av == null || !Number.isFinite(av);
  const bMissing = bv == null || !Number.isFinite(bv);
  if (aMissing && bMissing) return a.title.localeCompare(b.title);
  if (aMissing) return 1;
  if (bMissing) return -1;
  const direction = sortDir === "asc" ? 1 : -1;
  const diff = (av - bv) * direction;
  if (diff !== 0) return diff;
  return a.title.localeCompare(b.title);
}

function adsSortValue(row: EnrichedRow, sortMode: SortMode): number | null {
  if (sortMode === "drr") return row.drr;
  if (sortMode === "profit") return row.profitAfterAds;
  if (sortMode === "clicks") return row.clicks;
  if (sortMode === "cr") return row.cr;
  if (sortMode === "orders") return row.orders;
  if (sortMode === "canceled") return row.canceled;
  if (sortMode === "spend_share") return row.spendShare;
  return row.sourceAdSpend || row.adSpend;
}

function enrichAdsRow(
  item: AdsRecord,
  index: number,
  campById: Map<number, AdCampaign>,
): EnrichedRow {
  const advertIds = normalizeAdvertIds(item);
  const advertId =
    num(item.advert_id ?? item.campaign_id) ??
    (advertIds.length === 1 ? advertIds[0] : null);
  const campaign = advertId != null ? campById.get(advertId) : undefined;
  const adSpend = num(item.ad_spend ?? item.spend ?? item.cost) ?? 0;
  const sourceAdSpend =
    num(item.source_ad_spend ?? item.ads_source_spend) ?? adSpend;
  const businessRevenue = num(item.business_revenue ?? item.revenue) ?? 0;
  const adRevenue =
    num(
      item.ad_revenue ??
        item.source_revenue ??
        item.attributed_revenue ??
        item.sum_price,
    ) ?? businessRevenue;
  const revenue = adRevenue > 0 ? adRevenue : businessRevenue;
  const drr =
    num(item.drr_percent ?? item.drr) ??
    (revenue > 0 && sourceAdSpend > 0
      ? (sourceAdSpend / revenue) * 100
      : revenue > 0 && adSpend > 0
        ? (adSpend / revenue) * 100
        : null);
  const profitAfterAds =
    num(item.profit_after_ads ?? item.net_profit ?? item.profit) ?? null;
  const views = num(item.views) ?? 0;
  const clicks = num(item.clicks) ?? 0;
  const orders = num(item.orders ?? item.orders_count) ?? 0;
  const shks = num(item.shks ?? item.ordered_items ?? item.ordered_qty) ?? 0;
  const canceled =
    num(item.canceled ?? item.cancelled ?? item.cancel_count) ?? 0;
  const ctr =
    num(item.ctr_percent ?? item.ctr) ??
    (views > 0 && clicks > 0 ? (clicks / views) * 100 : null);
  const cr =
    num(item.cr_percent ?? item.cr) ??
    (clicks > 0 && orders > 0 ? (orders / clicks) * 100 : null);
  const cpc =
    num(item.cpc) ??
    (clicks > 0 && sourceAdSpend > 0
      ? sourceAdSpend / clicks
      : clicks > 0 && adSpend > 0
        ? adSpend / clicks
        : null);
  const allocationStatus = normalizeAllocationStatus(
    item.ads_allocation_status ?? item.allocation_status,
  );
  const blockedReasons = Array.isArray(item.blocked_reasons)
    ? item.blocked_reasons.map(String)
    : [];
  const finalProfitAllowed = item.final_profit_allowed !== false;
  const hint = classifyHint({
    ...item,
    drr_percent: drr,
    profit_after_ads: profitAfterAds,
    ad_spend: adSpend,
    allocationStatus,
    blockedReasons,
    finalProfitAllowed,
  });
  const nmId = num(item.nm_id);
  const skuId = num(item.sku_id);

  return {
    key: `${skuId ?? "nm"}-${nmId ?? "x"}-${advertIds.join(".") || advertId || index}`,
    raw: item,
    skuId,
    nmId,
    title: String(
      item.title ?? item.name ?? item.vendor_code ?? `nm ${nmId ?? "—"}`,
    ),
    vendorCode: item.vendor_code ? String(item.vendor_code) : null,
    level: String(item.level ?? (skuId ? "sku" : "nm")),
    advertId,
    advertIds,
    campaignName: String(
      item.campaign_name ??
        campaign?.name ??
        (advertIds.length > 1
          ? `${advertIds.length} кампаний`
          : "Кампания без названия"),
    ),
    campaignCount: num(item.campaign_count) ?? advertIds.length,
    campaign,
    views,
    clicks,
    orders,
    shks,
    atbs: num(item.atbs) ?? 0,
    canceled,
    ctr,
    cr,
    cpc,
    adRevenue,
    businessRevenue,
    spendShare: num(item.spend_share_percent ?? item.spend_share),
    revenue,
    adSpend,
    rawAdSpend: num(item.raw_ad_spend) ?? Math.max(adSpend, sourceAdSpend),
    sourceAdSpend,
    overallocatedAdSpend: num(item.overallocated_ad_spend) ?? 0,
    unallocatedAdSpend: num(item.unallocated_ad_spend) ?? 0,
    drr,
    profitAfterAds,
    stockQty: num(item.stock_qty),
    daysOfStock: num(item.days_of_stock),
    allocationStatus,
    allocationLabel: String(
      item.ads_allocation_status_label ??
        allocationStatusLabel(allocationStatus),
    ),
    finalProfitAllowed,
    confidence: String(item.confidence ?? "medium"),
    trustState: String(item.trust_state ?? ""),
    blockedReasons,
    hint,
  };
}

function classifyHint(
  item: AdsRecord & {
    blockedReasons?: string[];
    finalProfitAllowed?: boolean;
    allocationStatus?: unknown;
  },
): Exclude<AdsHintFilter, "all"> {
  const explicit = String(
    item.action_hint ?? item.hint ?? item.action ?? "",
  ).toUpperCase();
  if (explicit in HINT_COPY) return explicit as Exclude<AdsHintFilter, "all">;
  if (
    item.finalProfitAllowed === false ||
    (item.blockedReasons ?? []).length > 0
  )
    return "DATA_FIX";
  const allocationStatus = normalizeAllocationStatus(
    item.allocationStatus ??
      item.ads_allocation_status ??
      item.allocation_status,
  );
  if (allocationStatus !== "matched" && allocationStatus !== "no_source_data")
    return "AD_ALLOCATION_REVIEW";
  const drr = num(item.drr_percent ?? item.drr);
  const profit = num(item.profit_after_ads ?? item.net_profit);
  const spend = num(item.ad_spend ?? item.spend ?? item.cost) ?? 0;
  if (spend <= 0) return "WATCH";
  if ((drr != null && drr >= 25) || (profit != null && profit < 0))
    return "AD_PAUSE_REVIEW";
  if (drr != null && drr <= 7 && (profit ?? 0) > 0) return "AD_SCALE_REVIEW";
  return "WATCH";
}

function normalizeAdvertIds(item: AdsRecord): number[] {
  const raw = Array.isArray(item.advert_ids) ? item.advert_ids : [];
  const ids = raw.map(num).filter((value): value is number => value != null);
  const single = num(item.advert_id ?? item.campaign_id);
  if (single != null && !ids.includes(single)) ids.unshift(single);
  return [...new Set(ids)];
}

function normalizeAllocationStatus(status: unknown): string {
  const value = String(status ?? "")
    .trim()
    .toLowerCase();
  if (value === "linked" || value === "allocated") return "matched";
  if (value === "unallocated") return "partial";
  if (value === "no_source") return "no_source_data";
  return value || "no_source_data";
}

function allocationStatusLabel(status: string): string {
  const map: Record<string, string> = {
    matched: "Привязано",
    partial: "Частично",
    overallocated: "Переаллокация",
    no_source_data: "Нет источника",
  };
  return map[normalizeAllocationStatus(status)] ?? status;
}

function campaignStatusLabel(status?: number | null): string {
  const map: Record<number, string> = {
    4: "Готова",
    7: "Завершена",
    8: "Отклонена",
    9: "Активна",
    11: "Пауза",
  };
  return status == null ? "—" : (map[status] ?? `Статус ${status}`);
}

function campaignStatusTone(status?: number | null): string {
  if (status === 9) return toneClass("success");
  if (status === 11 || status === 4) return toneClass("warning");
  if (status === 8) return toneClass("danger");
  return toneClass("default");
}

function campaignTypeLabel(type?: number | null): string {
  const map: Record<number, string> = {
    4: "Каталог",
    5: "Карточка",
    6: "Поиск",
    7: "Рекомендации",
    8: "Автоматическая",
    9: "Аукцион",
  };
  return type == null ? "тип не указан" : (map[type] ?? `тип ${type}`);
}

function toneClass(tone: Tone): string {
  if (tone === "success") return "border-success/30 bg-success/10 text-success";
  if (tone === "warning") return "border-warning/30 bg-warning/10 text-warning";
  if (tone === "danger")
    return "border-destructive/30 bg-destructive/10 text-destructive";
  if (tone === "info") return "border-info/30 bg-info/10 text-info";
  return "border-border bg-muted/50 text-muted-foreground";
}

function toneIconClass(tone: Tone): string {
  if (tone === "success") return "bg-success/10 text-success";
  if (tone === "warning") return "bg-warning/10 text-warning";
  if (tone === "danger") return "bg-destructive/10 text-destructive";
  if (tone === "info") return "bg-info/10 text-info";
  return "bg-muted text-muted-foreground";
}

function valueToneClass(tone: Tone): string {
  if (tone === "success") return "text-success";
  if (tone === "warning") return "text-warning";
  if (tone === "danger") return "text-destructive";
  if (tone === "info") return "text-info";
  return "";
}

function pageItems<T>(data: unknown): T[] {
  if (!data) return [];
  if (Array.isArray(data)) return data as T[];
  if (!isRecord(data)) return [];
  return ((data.items ?? data.rows ?? data.articles ?? []) as T[]) ?? [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function sum<T>(
  items: T[],
  pick: (item: T) => number | null | undefined,
): number {
  return items.reduce((total, item) => total + (pick(item) ?? 0), 0);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function num(value: unknown): number | null {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function textOrNull(value: unknown): string | null {
  if (value == null || value === "") return null;
  return String(value);
}
