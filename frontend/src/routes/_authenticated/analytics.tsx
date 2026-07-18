/* eslint-disable @typescript-eslint/no-explicit-any */
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  BarChart3,
  Boxes,
  CalendarDays,
  ChevronRight,
  CheckCircle2,
  Database,
  DollarSign,
  Download,
  Eye,
  Filter,
  Gauge,
  LineChart,
  Loader2,
  Megaphone,
  PackageSearch,
  RefreshCw,
  ReceiptText,
  Search,
  ShoppingCart,
  SlidersHorizontal,
  Tags,
  TrendingDown,
  TrendingUp,
  Warehouse,
  X,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";

import { DataBrowser, type Column } from "@/components/DataBrowser";
import { EndpointError } from "@/components/EndpointError";
import { PageHeader, PageShell } from "@/components/PageShell";
import { GranularityBadge } from "@/components/granularity";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type Row } from "@/lib/api";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";
import { API_ENDPOINTS } from "@/lib/endpoints";
import {
  formatDate,
  formatMoney,
  formatMoneyCompact,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

export const Route = createFileRoute("/_authenticated/analytics")({
  component: AnalyticsPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

type ComparisonMetric = {
  value: number | null;
  previous_value?: number | null;
  delta?: number | null;
  delta_percent?: number | null;
};

type AnalyticsOverview = {
  account_id: number;
  period: {
    date_from: string;
    date_to: string;
    previous_date_from: string;
    previous_date_to: string;
  };
  summary: Record<string, ComparisonMetric> & {
    hidden_blocked: number;
    hidden_shadowed: number;
  };
  money: MoneySummary;
  ads: AdsSummary;
  stock: StockSummary;
  prices: PriceSummary;
  trend: TrendPoint[];
  products: ProductRow[];
  regions: RegionRow[];
  data_sources: DataSourceStatus[];
  api_capabilities: ApiCapability[];
  recommendations: Recommendation[];
  export_datasets: string[];
};

type MoneySummary = {
  revenue: ComparisonMetric;
  for_pay: ComparisonMetric;
  profit: ComparisonMetric;
  margin_percent: ComparisonMetric;
  wb_expenses: ComparisonMetric;
  seller_expenses: ComparisonMetric;
  cost_price: ComparisonMetric;
  orders: ComparisonMetric;
  returns: ComparisonMetric;
  return_rate: ComparisonMetric;
  rows_count: number;
};

type AdsSummary = {
  spend: ComparisonMetric;
  views: ComparisonMetric;
  clicks: ComparisonMetric;
  orders: ComparisonMetric;
  ctr: ComparisonMetric;
  cpc: ComparisonMetric;
  drr_percent: ComparisonMetric;
  roas: ComparisonMetric;
  rows_count: number;
};

type StockSummary = {
  stock_qty: number;
  full_stock_qty: number;
  in_way_to_client: number;
  in_way_from_client: number;
  out_of_stock_risk: number;
  dead_stock: number;
  avg_days_of_stock?: number | null;
  latest_date?: string | null;
  rows_count: number;
};

type PriceSummary = {
  avg_price?: number | null;
  avg_discounted_price?: number | null;
  avg_discount_percent?: number | null;
  bad_turnover: number;
  quarantine: number;
  goods_count: number;
  size_count: number;
};

type TrendPoint = {
  date: string;
  open_count: number;
  cart_count: number;
  order_count: number;
  buyout_count: number;
  cancel_count: number;
  revenue: number;
  units_sold: number;
  for_pay: number;
  profit: number;
  ad_spend: number;
  stock_qty: number;
  cart_rate: number | null;
  order_rate: number | null;
  buyout_rate: number | null;
};

type ProductRow = {
  nm_id: number;
  vendor_code?: string | null;
  title?: string | null;
  brand_name?: string | null;
  subject_name?: string | null;
  open_count: number;
  cart_count: number;
  order_count: number;
  buyout_count: number;
  cancel_count: number;
  revenue: number;
  units_sold: number;
  for_pay?: number | null;
  profit?: number | null;
  margin_percent?: number | null;
  wb_expenses?: number | null;
  ad_spend?: number | null;
  drr_percent?: number | null;
  stock_qty?: number | null;
  days_of_stock?: number | null;
  current_price?: number | null;
  current_discounted_price?: number | null;
  return_count?: number | null;
  return_rate?: number | null;
  row_source: string;
  cart_rate: number | null;
  order_rate: number | null;
  buyout_rate: number | null;
  open_delta_percent?: number | null;
  order_delta_percent?: number | null;
  revenue_delta_percent?: number | null;
  status: "ok" | "watch" | "warning" | "danger" | string;
  issue?: string | null;
  action?: string | null;
};

type RegionRow = {
  country_name?: string | null;
  region_name?: string | null;
  city_name?: string | null;
  federal_district?: string | null;
  revenue: number;
  units_sold: number;
  cards_count: number;
  share_percent?: number | null;
};

type DataSourceStatus = {
  key: string;
  label: string;
  status: string;
  rows: number;
  note?: string | null;
};

type ApiCapability = {
  key: string;
  label: string;
  endpoint: string;
  status: string;
  note?: string | null;
};

type Recommendation = {
  severity: "info" | "warning" | "danger" | string;
  title: string;
  detail: string;
  action: string;
  source?: string | null;
};

type AnalyticsFilters = {
  search: string;
  nmId: string;
  vendorCode: string;
  brandName: string;
  subjectName: string;
  regionName: string;
  countryName: string;
};

type MetricKey =
  | "revenue"
  | "profit"
  | "ad_spend"
  | "stock_qty"
  | "order_count"
  | "cart_rate"
  | "order_rate"
  | "buyout_rate"
  | "hidden";

type DrillTarget =
  | { kind: "metric"; key: MetricKey }
  | { kind: "product"; nmId: number }
  | { kind: "region"; regionName?: string | null; countryName?: string | null }
  | { kind: "day"; date: string };

type MetricDefinition = {
  key: MetricKey;
  title: string;
  subtitle: string;
  icon: LucideIcon;
  metric: ComparisonMetric;
  format: (value: number | null | undefined) => string;
  tone: "good" | "warning" | "danger" | "neutral";
};

const emptyFilters: AnalyticsFilters = {
  search: "",
  nmId: "",
  vendorCode: "",
  brandName: "",
  subjectName: "",
  regionName: "",
  countryName: "",
};

const funnelCols: Column<Row>[] = [
  { header: "Уровень", cell: (r) => <GranularityBadge row={r as any} /> },
  {
    header: "Дата",
    sortKey: "stat_date",
    cell: (r) => (
      <span className="text-xs">{formatDate(r.stat_date as string)}</span>
    ),
  },
  {
    header: "nm_id",
    sortKey: "nm_id",
    cell: (r) => (
      <span className="font-mono text-xs">{String(r.nm_id ?? "—")}</span>
    ),
  },
  {
    header: "Артикул",
    sortKey: "vendor_code",
    cell: (r) => (
      <span className="text-xs">{String(r.vendor_code ?? "—")}</span>
    ),
  },
  {
    header: "Название",
    sortKey: "title",
    cell: (r) => (
      <span className="line-clamp-1 max-w-[320px] text-xs">
        {String(r.title ?? "—")}
      </span>
    ),
  },
  {
    header: "Открытия",
    sortKey: "open_count",
    align: "right",
    cell: (r) => formatNumber(Number(r.open_count ?? 0)),
  },
  {
    header: "Корзина",
    sortKey: "cart_count",
    align: "right",
    cell: (r) => formatNumber(Number(r.cart_count ?? 0)),
  },
  {
    header: "Заказы",
    sortKey: "order_count",
    align: "right",
    cell: (r) => formatNumber(Number(r.order_count ?? 0)),
  },
  {
    header: "Выкупы",
    sortKey: "buyout_count",
    align: "right",
    cell: (r) => formatNumber(Number(r.buyout_count ?? 0)),
  },
  {
    header: "Выкуп",
    sortKey: "buyout_percent",
    align: "right",
    cell: (r) => formatPercent(Number(r.buyout_percent ?? 0)),
  },
];

const regionCols: Column<Row>[] = [
  { header: "Уровень", cell: (r) => <GranularityBadge row={r as any} /> },
  {
    header: "Дата",
    sortKey: "stat_date",
    cell: (r) => (
      <span className="text-xs">{formatDate(r.stat_date as string)}</span>
    ),
  },
  {
    header: "nm_id",
    sortKey: "nm_id",
    cell: (r) => (
      <span className="font-mono text-xs">{String(r.nm_id ?? "—")}</span>
    ),
  },
  {
    header: "Артикул",
    sortKey: "vendor_code",
    cell: (r) => (
      <span className="text-xs">{String(r.vendor_code ?? "—")}</span>
    ),
  },
  {
    header: "Страна",
    sortKey: "country_name",
    cell: (r) => (
      <span className="text-xs">{String(r.country_name ?? "—")}</span>
    ),
  },
  {
    header: "Регион",
    sortKey: "region_name",
    cell: (r) => (
      <span className="text-xs">{String(r.region_name ?? "—")}</span>
    ),
  },
  {
    header: "Город",
    sortKey: "city_name",
    cell: (r) => <span className="text-xs">{String(r.city_name ?? "—")}</span>,
  },
  {
    header: "Шт",
    sortKey: "sale_quantity",
    align: "right",
    cell: (r) => formatNumber(Number(r.sale_quantity ?? 0)),
  },
  {
    header: "Выручка",
    sortKey: "sale_amount",
    align: "right",
    cell: (r) => formatMoneyCompact(Number(r.sale_amount ?? 0)),
  },
];

const chartColors = {
  open: "var(--color-chart-1)",
  cart: "var(--color-chart-2)",
  orders: "var(--color-chart-3)",
  buyout: "var(--color-chart-5)",
  revenue: "var(--color-chart-4)",
  profit: "var(--color-chart-2)",
  ads: "var(--destructive)",
  warning: "var(--warning)",
};

function buildMetricDefinitions(data: AnalyticsOverview): MetricDefinition[] {
  const s = data.summary;
  const hiddenTotal = (s.hidden_blocked || 0) + (s.hidden_shadowed || 0);
  return [
    {
      key: "revenue",
      title: "Выручка",
      subtitle: "Финальная товарная витрина",
      icon: DollarSign,
      metric: s.revenue,
      format: formatMoneyCompact,
      tone: "neutral",
    },
    {
      key: "profit",
      title: "Прибыль",
      subtitle: "После расходов и рекламы",
      icon: ReceiptText,
      metric: data.money.profit,
      format: formatMoneyCompact,
      tone:
        (data.money.profit.value ?? 0) < 0
          ? "danger"
          : (data.money.margin_percent.value ?? 0) >= 15
            ? "good"
            : "warning",
    },
    {
      key: "ad_spend",
      title: "Реклама",
      subtitle: "Расход на продвижение WB",
      icon: Megaphone,
      metric: data.ads.spend,
      format: formatMoneyCompact,
      tone:
        (data.ads.drr_percent.value ?? 0) > 25
          ? "danger"
          : (data.ads.drr_percent.value ?? 0) > 12
            ? "warning"
            : "neutral",
    },
    {
      key: "stock_qty",
      title: "Остаток",
      subtitle: "Последний снимок склада",
      icon: Warehouse,
      metric: {
        value: data.stock.stock_qty,
        previous_value: null,
        delta: null,
        delta_percent: null,
      },
      format: formatNumber,
      tone: data.stock.out_of_stock_risk ? "warning" : "neutral",
    },
    {
      key: "order_count",
      title: "Заказы",
      subtitle: "Оформленные заказы",
      icon: ShoppingCart,
      metric: s.order_count,
      format: formatNumber,
      tone: "neutral",
    },
    {
      key: "cart_rate",
      title: "Открытие → корзина",
      subtitle: "Переход в корзину",
      icon: Eye,
      metric: s.cart_rate,
      format: (v) => formatPercent(v, 2),
      tone: rateTone(s.cart_rate.value, 4, 8),
    },
    {
      key: "order_rate",
      title: "Корзина → заказ",
      subtitle: "Переход в заказ",
      icon: Filter,
      metric: s.order_rate,
      format: (v) => formatPercent(v, 2),
      tone: rateTone(s.order_rate.value, 20, 35),
    },
    {
      key: "buyout_rate",
      title: "Доля выкупа",
      subtitle: "Заказ → выкуп",
      icon: CheckCircle2,
      metric: s.buyout_rate,
      format: (v) => formatPercent(v, 1),
      tone: rateTone(s.buyout_rate.value, 60, 75),
    },
    {
      key: "hidden",
      title: "Скрытые карточки",
      subtitle: "Блокировки и скрытия",
      icon: AlertTriangle,
      metric: {
        value: hiddenTotal,
        previous_value: null,
        delta: null,
        delta_percent: null,
      },
      format: formatNumber,
      tone: hiddenTotal ? "danger" : "good",
    },
  ];
}

function AnalyticsPage() {
  const { activeId } = useAccounts();
  const { from: dateFrom, to: dateTo } = useDateRange();
  const [filters, setFilters] = useState<AnalyticsFilters>(emptyFilters);
  const debouncedFilters = useDebouncedValue(filters, 350);
  const [exporting, setExporting] = useState<string | null>(null);
  const [drillTarget, setDrillTarget] = useState<DrillTarget>({
    kind: "metric",
    key: "revenue",
  });
  const detailPanelRef = useRef<HTMLElement | null>(null);

  const revealDetail = useCallback((target: DrillTarget) => {
    setDrillTarget(target);
    window.requestAnimationFrame(() => {
      detailPanelRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }, []);

  const query = useMemo(
    () => ({
      account_id: activeId ?? undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      search: debouncedFilters.search || undefined,
      nm_id: debouncedFilters.nmId ? Number(debouncedFilters.nmId) : undefined,
      vendor_code: debouncedFilters.vendorCode || undefined,
      brand_name: debouncedFilters.brandName || undefined,
      subject_name: debouncedFilters.subjectName || undefined,
      region_name: debouncedFilters.regionName || undefined,
      country_name: debouncedFilters.countryName || undefined,
    }),
    [activeId, dateFrom, dateTo, debouncedFilters],
  );

  const overviewQ = useQuery({
    queryKey: ["analytics-overview", query],
    enabled: !!activeId,
    queryFn: () =>
      api<AnalyticsOverview>(API_ENDPOINTS.analytics.overview, { query }),
    retry: false,
    staleTime: 60_000,
  });

  const data = overviewQ.data;
  const hasActiveFilters = Object.values(filters).some(Boolean);
  const funnelStages = buildFunnelStages(data);
  const rawExtraQuery = {
    date_from: query.date_from,
    date_to: query.date_to,
    search: query.search,
    nm_id: query.nm_id,
    vendor_code: query.vendor_code,
    brand_name: query.brand_name,
    subject_name: query.subject_name,
    region_name: query.region_name,
    country_name: query.country_name,
  };

  const updateFilter = (key: keyof AnalyticsFilters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const resetFilters = () => setFilters(emptyFilters);

  const exportCsv = async (dataset: string) => {
    if (!activeId || exporting) return;
    setExporting(dataset);
    try {
      const res = await api<Response>(API_ENDPOINTS.analytics.exportCsv, {
        raw: true,
        query: { ...query, dataset },
      });
      if (!res.ok) throw new Error(`Ошибка экспорта (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `analytics_${dataset}_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      toast.success("Файл выгружается");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Не удалось скачать файл",
      );
    } finally {
      setExporting(null);
    }
  };

  if (!activeId) {
    return (
      <PageShell>
        <PageHeader
          title="Аналитика"
          description="Воронка, регионы, карточки и точные детализации по данным WB."
        />
        <NoAccountSelected />
      </PageShell>
    );
  }

  if (overviewQ.error) {
    return (
      <PageShell>
        <EndpointError
          error={overviewQ.error}
          reset={() => void overviewQ.refetch()}
        />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="Аналитика"
        description={
          data
            ? `${formatDate(data.period.date_from)} — ${formatDate(data.period.date_to)}`
            : "Воронка, регионы и карточки по данным WB."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void overviewQ.refetch()}
              disabled={overviewQ.isFetching}
            >
              {overviewQ.isFetching ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              )}
              Обновить
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void exportCsv("products")}
              disabled={!data || !!exporting}
            >
              {exporting === "products" ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="mr-1.5 h-3.5 w-3.5" />
              )}
              Товары
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void exportCsv("regions")}
              disabled={!data || !!exporting}
            >
              {exporting === "regions" ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="mr-1.5 h-3.5 w-3.5" />
              )}
              Регионы
            </Button>
          </div>
        }
      />

      <FiltersBar
        filters={filters}
        hasActiveFilters={hasActiveFilters}
        onChange={updateFilter}
        onReset={resetFilters}
      />

      {overviewQ.isLoading || !data ? (
        <AnalyticsSkeleton />
      ) : (
        <div className="space-y-4">
          <MetricGrid
            data={data}
            selected={drillTarget}
            onSelect={revealDetail}
          />

          <DrilldownPanel
            data={data}
            target={drillTarget}
            baseQuery={query}
            onTargetChange={revealDetail}
            panelRef={detailPanelRef}
          />

          <BusinessPulse data={data} />

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(360px,0.85fr)]">
            <TrendPanel
              data={data}
              onSelectDay={(date) => revealDetail({ kind: "day", date })}
            />
            <FunnelPanel stages={funnelStages} summary={data.summary} />
          </div>

          <Tabs defaultValue="business" className="space-y-3">
            <TabsList className="h-auto flex-wrap justify-start rounded-md">
              <TabsTrigger value="business" className="gap-1.5">
                <ReceiptText className="h-3.5 w-3.5" />
                Деньги и контроль
              </TabsTrigger>
              <TabsTrigger value="products" className="gap-1.5">
                <PackageSearch className="h-3.5 w-3.5" />
                Карточки
              </TabsTrigger>
              <TabsTrigger value="regions" className="gap-1.5">
                <BarChart3 className="h-3.5 w-3.5" />
                Регионы
              </TabsTrigger>
              <TabsTrigger value="insights" className="gap-1.5">
                <Gauge className="h-3.5 w-3.5" />
                Сигналы
              </TabsTrigger>
              <TabsTrigger value="raw" className="gap-1.5">
                <Database className="h-3.5 w-3.5" />
                Исходные данные WB
              </TabsTrigger>
              <TabsTrigger value="api" className="gap-1.5">
                <SlidersHorizontal className="h-3.5 w-3.5" />
                Интеграции WB
              </TabsTrigger>
            </TabsList>

            <TabsContent value="business">
              <BusinessDeepPanel data={data} />
            </TabsContent>

            <TabsContent value="products">
              <ProductsTable
                rows={data.products}
                onSelect={(row) =>
                  setDrillTarget({ kind: "product", nmId: row.nm_id })
                }
                onExport={() => void exportCsv("products")}
                exporting={exporting === "products"}
              />
            </TabsContent>

            <TabsContent value="regions">
              <RegionsPanel
                rows={data.regions}
                onSelect={(row) =>
                  setDrillTarget({
                    kind: "region",
                    regionName: row.region_name,
                    countryName: row.country_name,
                  })
                }
                onExport={() => void exportCsv("regions")}
                exporting={exporting === "regions"}
              />
            </TabsContent>

            <TabsContent value="insights">
              <InsightsPanel data={data} />
            </TabsContent>

            <TabsContent value="raw">
              <RawDataTabs extraQuery={rawExtraQuery} />
            </TabsContent>

            <TabsContent value="api">
              <ApiCoveragePanel data={data} />
            </TabsContent>
          </Tabs>
        </div>
      )}
    </PageShell>
  );
}

function FiltersBar({
  filters,
  hasActiveFilters,
  onChange,
  onReset,
}: {
  filters: AnalyticsFilters;
  hasActiveFilters: boolean;
  onChange: (key: keyof AnalyticsFilters, value: string) => void;
  onReset: () => void;
}) {
  const activeFilters = filterChips(filters);
  const activeCount = activeFilters.length;

  return (
    <div className="mb-4 rounded-md border bg-card shadow-sm">
      <div className="flex flex-col gap-3 p-3">
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filters.search}
              onChange={(event) => onChange("search", event.target.value)}
              placeholder="Название, артикул, бренд, категория, регион"
              className="h-11 rounded-md border-border/80 bg-background pl-9 pr-9 text-sm shadow-none"
            />
            {filters.search && (
              <button
                type="button"
                onClick={() => onChange("search", "")}
                className="absolute right-2 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <div className="flex shrink-0 gap-2">
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  className="h-11 gap-2 rounded-md px-3"
                >
                  <SlidersHorizontal className="h-4 w-4" />
                  Фильтры
                  {activeCount > 0 && (
                    <Badge variant="secondary" className="rounded-md px-1.5">
                      {activeCount}
                    </Badge>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent
                align="end"
                className="w-[min(560px,calc(100vw-24px))] rounded-md p-0"
              >
                <div className="border-b px-4 py-3">
                  <div className="text-sm font-semibold">Фильтры аналитики</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    Товар, бренд, категория и география
                  </div>
                </div>
                <div className="grid gap-3 p-4 sm:grid-cols-2">
                  <FilterInput
                    label="Артикул WB"
                    value={filters.nmId}
                    onChange={(v) => onChange("nmId", v)}
                    inputMode="numeric"
                  />
                  <FilterInput
                    label="Артикул продавца"
                    value={filters.vendorCode}
                    onChange={(v) => onChange("vendorCode", v)}
                  />
                  <FilterInput
                    label="Бренд"
                    value={filters.brandName}
                    onChange={(v) => onChange("brandName", v)}
                  />
                  <FilterInput
                    label="Категория"
                    value={filters.subjectName}
                    onChange={(v) => onChange("subjectName", v)}
                  />
                  <FilterInput
                    label="Регион"
                    value={filters.regionName}
                    onChange={(v) => onChange("regionName", v)}
                  />
                  <FilterInput
                    label="Страна"
                    value={filters.countryName}
                    onChange={(v) => onChange("countryName", v)}
                  />
                </div>
                <div className="flex items-center justify-between gap-2 border-t px-4 py-3">
                  <div className="text-xs text-muted-foreground">
                    {activeCount
                      ? `${activeCount} активно`
                      : "Фильтры не выбраны"}
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={onReset}
                    disabled={!hasActiveFilters}
                    className="gap-1.5"
                  >
                    <X className="h-3.5 w-3.5" />
                    Очистить
                  </Button>
                </div>
              </PopoverContent>
            </Popover>

            <Button
              type="button"
              variant="ghost"
              className="h-11 rounded-md px-3"
              onClick={onReset}
              disabled={!hasActiveFilters}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {activeFilters.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {activeFilters.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => onChange(item.key, "")}
                className="inline-flex max-w-full items-center gap-1.5 rounded-md border bg-muted/45 px-2.5 py-1 text-xs text-foreground transition hover:border-primary/40 hover:bg-muted"
              >
                <span className="text-muted-foreground">{item.label}</span>
                <span className="max-w-[180px] truncate font-medium">
                  {item.value}
                </span>
                <X className="h-3 w-3 text-muted-foreground" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function filterChips(filters: AnalyticsFilters): Array<{
  key: keyof AnalyticsFilters;
  label: string;
  value: string;
}> {
  const items: Array<{
    key: keyof AnalyticsFilters;
    label: string;
    value: string;
  }> = [
    { key: "search", label: "Поиск", value: filters.search },
    { key: "nmId", label: "Артикул WB", value: filters.nmId },
    { key: "vendorCode", label: "Артикул", value: filters.vendorCode },
    { key: "brandName", label: "Бренд", value: filters.brandName },
    { key: "subjectName", label: "Категория", value: filters.subjectName },
    { key: "regionName", label: "Регион", value: filters.regionName },
    { key: "countryName", label: "Страна", value: filters.countryName },
  ];
  return items.filter((item) => item.value.trim().length > 0);
}

function FilterInput({
  label,
  value,
  onChange,
  icon: Icon,
  placeholder,
  inputMode,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  icon?: LucideIcon;
  placeholder?: string;
  inputMode?: "numeric";
}) {
  return (
    <div className="min-w-0">
      <Label className="text-[11px] font-medium text-muted-foreground">
        {label}
      </Label>
      <div className="relative mt-1">
        {Icon && (
          <Icon className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        )}
        <Input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          inputMode={inputMode}
          className={cn("h-9 rounded-md", Icon && "pl-8")}
        />
      </div>
    </div>
  );
}

function MetricGrid({
  data,
  selected,
  onSelect,
}: {
  data: AnalyticsOverview;
  selected: DrillTarget;
  onSelect: (target: DrillTarget) => void;
}) {
  const metrics = buildMetricDefinitions(data);

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5">
      {metrics.map((item) => (
        <MetricCard
          key={item.key}
          title={item.title}
          subtitle={item.subtitle}
          icon={item.icon}
          metric={item.metric}
          format={item.format}
          tone={item.tone}
          active={selected.kind === "metric" && selected.key === item.key}
          onClick={() => onSelect({ kind: "metric", key: item.key })}
        />
      ))}
    </div>
  );
}

function MetricCard({
  title,
  subtitle,
  icon: Icon,
  metric,
  format,
  tone,
  active,
  onClick,
}: {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  metric: ComparisonMetric;
  format: (value: number | null | undefined) => string;
  tone: "good" | "warning" | "danger" | "neutral";
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Card
      className={cn(
        "relative overflow-hidden rounded-md transition hover:-translate-y-0.5 hover:shadow-md",
        toneBorder(tone),
        active &&
          "border-primary bg-primary/[0.03] shadow-lg shadow-primary/15 ring-2 ring-primary/20 before:absolute before:inset-x-0 before:top-0 before:h-1 before:bg-primary",
      )}
    >
      <button
        type="button"
        onClick={onClick}
        aria-pressed={active}
        aria-controls="analytics-detail-panel"
        className="block h-full w-full rounded-md p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] font-medium uppercase text-muted-foreground">
              {title}
            </div>
            <div className="mt-1 truncate text-xl font-semibold tabular-nums">
              {format(metric.value)}
            </div>
            <div className="mt-1 line-clamp-1 text-[11px] text-muted-foreground">
              {subtitle}
            </div>
          </div>
          <div className={cn("rounded-md border p-2", toneIcon(tone))}>
            <Icon className="h-4 w-4" />
          </div>
        </div>
        <DeltaLine metric={metric} />
      </button>
    </Card>
  );
}

function BusinessPulse({ data }: { data: AnalyticsOverview }) {
  const cards = [
    {
      key: "money",
      title: "Движение денег",
      icon: DollarSign,
      tone: "emerald",
      primary: formatMoneyCompact(data.money.for_pay.value),
      primaryLabel: "К перечислению WB",
      rows: [
        ["Прибыль", formatMoneyCompact(data.money.profit.value)],
        ["Маржа", formatPercent(data.money.margin_percent.value, 1)],
        ["Расходы WB", formatMoneyCompact(data.money.wb_expenses.value)],
      ],
      footer: `${formatNumber(data.money.rows_count)} строк финансовой витрины`,
    },
    {
      key: "ads",
      title: "Реклама",
      icon: Megaphone,
      tone: "sky",
      primary: formatMoneyCompact(data.ads.spend.value),
      primaryLabel: "Расход",
      rows: [
        ["ДРР", formatPercent(data.ads.drr_percent.value, 1)],
        ["Клики", formatNumber(data.ads.clicks.value)],
        ["Кликабельность", formatPercent(data.ads.ctr.value, 2)],
      ],
      footer: `${formatNumber(data.ads.rows_count)} строк рекламы`,
    },
    {
      key: "stock",
      title: "Склад",
      icon: Warehouse,
      tone: "amber",
      primary: formatNumber(data.stock.stock_qty),
      primaryLabel: "Остаток",
      rows: [
        ["В пути к клиенту", formatNumber(data.stock.in_way_to_client)],
        ["Риск обнуления", formatNumber(data.stock.out_of_stock_risk)],
        ["Неликвид", formatNumber(data.stock.dead_stock)],
      ],
      footer: data.stock.latest_date
        ? `снимок ${formatDate(data.stock.latest_date)}`
        : "снимок не найден",
    },
    {
      key: "prices",
      title: "Цены",
      icon: Tags,
      tone: "rose",
      primary: formatMoneyCompact(data.prices.avg_discounted_price),
      primaryLabel: "Цена после скидки",
      rows: [
        ["Цена до скидки", formatMoneyCompact(data.prices.avg_price)],
        ["Средняя скидка", formatPercent(data.prices.avg_discount_percent, 1)],
        ["Карантин", formatNumber(data.prices.quarantine)],
      ],
      footer: `${formatNumber(data.prices.goods_count)} товаров, ${formatNumber(data.prices.size_count)} размеров`,
    },
  ] as const;

  return (
    <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-4">
      {cards.map(({ key, ...card }) => (
        <BusinessDomainCard key={key} {...card} />
      ))}
    </div>
  );
}

function BusinessDomainCard({
  title,
  icon: Icon,
  tone,
  primary,
  primaryLabel,
  rows,
  footer,
}: {
  title: string;
  icon: LucideIcon;
  tone: "emerald" | "sky" | "amber" | "rose";
  primary: ReactNode;
  primaryLabel: string;
  rows: readonly (readonly [string, ReactNode])[];
  footer: string;
}) {
  return (
    <Card className={cn("rounded-md border-l-4", domainTone(tone))}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Icon className="h-4 w-4" />
              {title}
            </div>
            <div className="mt-3 text-2xl font-semibold tabular-nums">
              {primary}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {primaryLabel}
            </div>
          </div>
          <div className={cn("rounded-md border p-2", domainIconTone(tone))}>
            <Icon className="h-4 w-4" />
          </div>
        </div>
        <div className="mt-4 grid gap-2">
          {rows.map(([label, value]) => (
            <div
              key={label}
              className="flex items-center justify-between gap-3 rounded-md bg-muted/35 px-2.5 py-2 text-sm"
            >
              <span className="text-muted-foreground">{label}</span>
              <span className="font-medium tabular-nums">{value}</span>
            </div>
          ))}
        </div>
        <div className="mt-3 truncate text-xs text-muted-foreground">
          {footer}
        </div>
      </CardContent>
    </Card>
  );
}

function TrendPanel({
  data,
  onSelectDay,
}: {
  data: AnalyticsOverview;
  onSelectDay: (date: string) => void;
}) {
  return (
    <Card className="rounded-md">
      <CardHeader className="p-4 pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <LineChart className="h-4 w-4 text-primary" />
            Воронка и выручка
          </CardTitle>
          <Badge variant="outline" className="rounded-md">
            {data.trend.length} дн.
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        <div className="h-[330px] min-h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={data.trend}
              margin={{ top: 18, right: 16, left: 0, bottom: 0 }}
              onClick={(state: any) => {
                const point = state?.activePayload?.[0]?.payload as
                  | TrendPoint
                  | undefined;
                if (point?.date) onSelectDay(point.date);
              }}
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
                yAxisId="left"
                tickLine={false}
                axisLine={false}
                width={44}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tickFormatter={(value) => formatMoneyCompact(Number(value))}
                tickLine={false}
                axisLine={false}
                width={58}
              />
              <RechartsTooltip content={<TrendTooltip />} />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="open_count"
                name="Открытия"
                stroke={chartColors.open}
                fill={chartColors.open}
                fillOpacity={0.12}
                strokeWidth={2}
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="cart_count"
                name="Корзина"
                stroke={chartColors.cart}
                strokeWidth={2}
                dot={false}
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="order_count"
                name="Заказы"
                stroke={chartColors.orders}
                strokeWidth={2}
                dot={false}
              />
              <Bar
                yAxisId="right"
                dataKey="revenue"
                name="Выручка"
                fill={chartColors.revenue}
                radius={[3, 3, 0, 0]}
                barSize={18}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="profit"
                name="Прибыль"
                stroke={chartColors.profit}
                strokeWidth={2}
                dot={false}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="ad_spend"
                name="Реклама"
                stroke={chartColors.ads}
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function FunnelPanel({
  stages,
  summary,
}: {
  stages: FunnelStage[];
  summary: AnalyticsOverview["summary"];
}) {
  return (
    <Card className="rounded-md">
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Gauge className="h-4 w-4 text-primary" />
          Панель конверсий
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-4 pt-0">
        <div className="space-y-3">
          {stages.map((stage) => (
            <div key={stage.key} className="space-y-1.5">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="font-medium">{stage.label}</span>
                <span className="tabular-nums text-muted-foreground">
                  {formatNumber(stage.value)}
                </span>
              </div>
              <Progress
                value={stage.width}
                className={cn("h-2 rounded-md", stage.colorClass)}
              />
              <div className="flex items-center justify-between gap-3 text-[11px] text-muted-foreground">
                <span>{stage.note}</span>
                <span>
                  {stage.rate == null ? "—" : formatPercent(stage.rate, 1)}
                </span>
              </div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2 border-t pt-3">
          <SmallStat
            label="Средний заказ"
            value={formatMoneyCompact(summary.avg_order_value.value)}
          />
          <SmallStat
            label="Отмены"
            value={formatNumber(summary.cancel_count.value)}
          />
          <SmallStat
            label="Карточки"
            value={formatNumber(summary.active_cards.value)}
          />
          <SmallStat
            label="Шт"
            value={formatNumber(summary.units_sold.value)}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function DrilldownPanel({
  data,
  target,
  baseQuery,
  onTargetChange,
  panelRef,
}: {
  data: AnalyticsOverview;
  target: DrillTarget;
  baseQuery: Record<string, string | number | undefined>;
  onTargetChange: (target: DrillTarget) => void;
  panelRef?: RefObject<HTMLElement | null>;
}) {
  const detailQuery = useQuery({
    queryKey: ["analytics-detail", baseQuery, target],
    enabled: target.kind !== "metric" && !!baseQuery.account_id,
    queryFn: () =>
      api<AnalyticsOverview>(API_ENDPOINTS.analytics.overview, {
        query: {
          ...baseQuery,
          ...queryForTarget(target),
          product_limit: 50,
          region_limit: 50,
        },
      }),
    retry: false,
    staleTime: 60_000,
  });

  const detail = target.kind === "metric" ? data : (detailQuery.data ?? data);
  const metricDefinitions = buildMetricDefinitions(detail);
  const selectedMetric =
    target.kind === "metric"
      ? metricDefinitions.find((item) => item.key === target.key)
      : null;
  const title = drillTitle(target, detail);
  const subtitle = drillSubtitle(target, detail);
  const primaryMetric =
    selectedMetric?.metric ??
    metricDefinitions.find((item) => item.key === "revenue")?.metric;
  const primaryKey = selectedMetric?.key ?? "revenue";
  const HeaderIcon =
    selectedMetric?.icon ??
    (target.kind === "product"
      ? PackageSearch
      : target.kind === "region"
        ? BarChart3
        : target.kind === "day"
          ? CalendarDays
          : LineChart);
  const currentPeriod = `${formatDate(detail.period.date_from)} — ${formatDate(detail.period.date_to)}`;
  const previousPeriod = `${formatDate(detail.period.previous_date_from)} — ${formatDate(detail.period.previous_date_to)}`;

  return (
    <section
      ref={panelRef}
      id="analytics-detail-panel"
      className="scroll-mt-4 overflow-hidden rounded-md border border-primary/25 bg-card shadow-sm ring-1 ring-primary/10"
    >
      <div className="border-b bg-muted/20 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline" className="rounded-md bg-background">
              Детализация
            </Badge>
            <ChevronRight className="h-3.5 w-3.5" />
            <span>{drillKindTitle(target)}</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {detailQuery.isFetching && (
              <Badge variant="outline" className="rounded-md bg-background">
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                Пересчёт
              </Badge>
            )}
            <Badge variant="outline" className="rounded-md">
              {currentPeriod}
            </Badge>
          </div>
        </div>

        <div className="mt-4 flex min-w-0 flex-wrap items-center gap-3">
          <div
            className={cn(
              "rounded-md border p-2.5",
              toneIcon(selectedMetric?.tone ?? "neutral"),
            )}
          >
            <HeaderIcon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-xl font-semibold">{title}</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>
          </div>
        </div>
      </div>

      <div className="space-y-4 p-4">
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1.25fr)_minmax(190px,0.55fr)_minmax(190px,0.55fr)_minmax(170px,0.45fr)]">
          <div className="rounded-md border bg-background p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs font-medium uppercase text-muted-foreground">
                Сейчас за выбранный период
              </div>
              <PeriodDeltaBadge metric={primaryMetric} />
            </div>
            <div className="mt-3 break-words text-3xl font-semibold tracking-normal tabular-nums">
              {formatMetricExact(primaryKey, primaryMetric?.value)}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>{selectedMetric?.title ?? "Выручка"}</span>
              <span className="text-border">•</span>
              <span>{currentPeriod}</span>
            </div>
          </div>

          <ExactStat
            label="Прошлый период"
            value={formatMetricExact(primaryKey, primaryMetric?.previous_value)}
            note={previousPeriod}
          />
          <ExactStat
            label="Изменение"
            value={formatMetricExact(primaryKey, primaryMetric?.delta)}
            note={formatPercent(primaryMetric?.delta_percent, 2)}
            tone={
              primaryMetric?.delta == null
                ? "neutral"
                : primaryMetric.delta < 0
                  ? "danger"
                  : "good"
            }
          />
          <ExactStat
            label="Дней в разрезе"
            value={formatNumber(detail.trend.length)}
            note="дневная динамика"
          />
        </div>

        <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]">
          <div className="space-y-4">
            <div className="rounded-md border bg-background/60 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <Gauge className="h-4 w-4 text-primary" />
                  Контрольные числа
                </div>
                <Badge variant="outline" className="rounded-md">
                  точные итоги
                </Badge>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <SmallStat
                  label="Открытия"
                  value={formatNumber(detail.summary.open_count.value)}
                />
                <SmallStat
                  label="Корзина"
                  value={formatNumber(detail.summary.cart_count.value)}
                />
                <SmallStat
                  label="Заказы"
                  value={formatNumber(detail.summary.order_count.value)}
                />
                <SmallStat
                  label="Выкупы"
                  value={formatNumber(detail.summary.buyout_count.value)}
                />
                <SmallStat
                  label="Выручка"
                  value={formatMoney(detail.summary.revenue.value)}
                />
                <SmallStat
                  label="Прибыль"
                  value={formatMoney(detail.money.profit.value)}
                />
                <SmallStat
                  label="Реклама"
                  value={formatMoney(detail.ads.spend.value)}
                />
                <SmallStat
                  label="Остаток"
                  value={formatNumber(detail.stock.stock_qty)}
                />
                <SmallStat
                  label="Штук продано"
                  value={formatNumber(detail.summary.units_sold.value)}
                />
              </div>
            </div>
            <RelatedLists data={detail} onTargetChange={onTargetChange} />
          </div>

          <DailyDetailTable
            rows={detail.trend}
            metricKey={primaryKey}
            onSelectDay={(date) => onTargetChange({ kind: "day", date })}
          />
        </div>
      </div>
    </section>
  );
}

function DailyDetailTable({
  rows,
  metricKey,
  onSelectDay,
}: {
  rows: TrendPoint[];
  metricKey: MetricKey;
  onSelectDay: (date: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-md border bg-background shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/25 px-3 py-2.5">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <CalendarDays className="h-4 w-4 text-primary" />
          Динамика по дням
        </div>
        <Badge variant="outline" className="rounded-md bg-background">
          {formatNumber(rows.length)} дней
        </Badge>
      </div>
      <div className="max-h-[620px] overflow-auto">
        <Table>
          <TableHeader className="sticky top-0 z-10 bg-background">
            <TableRow>
              <TableHead>Дата</TableHead>
              <TableHead className="text-right">Значение</TableHead>
              <TableHead className="text-right">Заказы</TableHead>
              <TableHead className="text-right">Выручка</TableHead>
              <TableHead className="w-[56px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.date} className="hover:bg-muted/40">
                <TableCell className="font-medium">
                  {formatDate(row.date)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatMetricExact(
                    metricKey,
                    metricValueForTrend(metricKey, row),
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatNumber(row.order_count)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatMoney(row.revenue)}
                </TableCell>
                <TableCell>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-8 w-8 rounded-md p-0"
                    onClick={() => onSelectDay(row.date)}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="py-8 text-center text-sm text-muted-foreground"
                >
                  Нет данных
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function RelatedLists({
  data,
  onTargetChange,
}: {
  data: AnalyticsOverview;
  onTargetChange: (target: DrillTarget) => void;
}) {
  return (
    <div className="grid gap-3">
      <div className="overflow-hidden rounded-md border bg-background shadow-sm">
        <div className="flex items-center gap-2 border-b bg-muted/25 px-3 py-2.5 text-sm font-semibold">
          <PackageSearch className="h-4 w-4 text-primary" />
          Связанные карточки
        </div>
        <div className="divide-y">
          {data.products.slice(0, 5).map((row, index) => (
            <button
              key={row.nm_id}
              type="button"
              className="block w-full px-3 py-2.5 text-left hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() =>
                onTargetChange({ kind: "product", nmId: row.nm_id })
              }
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                      {index + 1}
                    </span>
                    <span className="line-clamp-1 text-sm font-semibold">
                      {row.vendor_code || row.nm_id}
                    </span>
                  </div>
                  <div className="mt-1 line-clamp-1 text-xs text-muted-foreground">
                    {row.title || "—"}
                  </div>
                </div>
                <div className="shrink-0 text-right text-xs tabular-nums">
                  <div className="font-semibold">
                    {formatMoneyCompact(row.revenue)}
                  </div>
                  <div className="text-muted-foreground">
                    {formatNumber(row.order_count)} зак.
                  </div>
                </div>
              </div>
            </button>
          ))}
          {data.products.length === 0 && (
            <div className="px-3 py-5 text-center text-sm text-muted-foreground">
              Нет данных
            </div>
          )}
        </div>
      </div>

      <div className="overflow-hidden rounded-md border bg-background shadow-sm">
        <div className="flex items-center gap-2 border-b bg-muted/25 px-3 py-2.5 text-sm font-semibold">
          <BarChart3 className="h-4 w-4 text-primary" />
          Связанные регионы
        </div>
        <div className="divide-y">
          {data.regions.slice(0, 5).map((row, index) => (
            <button
              key={`${row.country_name}-${row.region_name}-${row.city_name}-${index}`}
              type="button"
              className="block w-full px-3 py-2.5 text-left hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() =>
                onTargetChange({
                  kind: "region",
                  regionName: row.region_name,
                  countryName: row.country_name,
                })
              }
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                      {index + 1}
                    </span>
                    <span className="line-clamp-1 text-sm font-semibold">
                      {row.region_name || row.country_name || "—"}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {formatMoneyCompact(row.revenue)} ·{" "}
                    {formatNumber(row.units_sold)} шт
                  </div>
                </div>
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                  {formatPercent(row.share_percent, 1)}
                </span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{
                    width: `${Math.min(100, Math.max(2, row.share_percent ?? 0))}%`,
                  }}
                />
              </div>
            </button>
          ))}
          {data.regions.length === 0 && (
            <div className="px-3 py-5 text-center text-sm text-muted-foreground">
              Нет данных
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ExactStat({
  label,
  value,
  note,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "good" | "warning" | "danger" | "neutral";
}) {
  return (
    <div
      className={cn(
        "rounded-md border bg-background/80 p-3 shadow-sm",
        tone === "good" &&
          "border-emerald-200 bg-emerald-50/50 dark:border-emerald-500/25 dark:bg-emerald-500/10",
        tone === "warning" &&
          "border-amber-200 bg-amber-50/50 dark:border-amber-500/25 dark:bg-amber-500/10",
        tone === "danger" &&
          "border-red-200 bg-red-50/50 dark:border-red-500/25 dark:bg-red-500/10",
      )}
    >
      <div className="text-[11px] font-medium uppercase text-muted-foreground">
        {label}
      </div>
      <div className="mt-2 break-words text-xl font-semibold tabular-nums">
        {value}
      </div>
      {note && <div className="mt-1 text-xs text-muted-foreground">{note}</div>}
    </div>
  );
}

function PeriodDeltaBadge({ metric }: { metric?: ComparisonMetric }) {
  if (!metric || metric.delta_percent == null) {
    return (
      <Badge variant="outline" className="rounded-md">
        нет прошлого периода
      </Badge>
    );
  }
  const positive = metric.delta_percent >= 0;
  const Icon = positive ? TrendingUp : TrendingDown;
  return (
    <Badge
      variant="outline"
      className={cn(
        "rounded-md tabular-nums",
        positive
          ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200"
          : "border-red-200 bg-red-50 text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200",
      )}
    >
      <Icon className="mr-1.5 h-3.5 w-3.5" />
      {formatPercent(metric.delta_percent, 2)}
    </Badge>
  );
}

function BusinessDeepPanel({ data }: { data: AnalyticsOverview }) {
  const revenue = data.money.revenue.value || 0;
  const expenseTotal =
    (data.money.wb_expenses.value || 0) +
    (data.money.seller_expenses.value || 0) +
    (data.ads.spend.value || 0);

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card className="rounded-md">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <DollarSign className="h-4 w-4 text-primary" />
            Разбор денег
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 p-4 pt-0">
          <div className="grid gap-3 sm:grid-cols-3">
            <ExactStat
              label="Выручка"
              value={formatMoneyCompact(data.money.revenue.value)}
              note="финальная витрина"
            />
            <ExactStat
              label="К перечислению"
              value={formatMoneyCompact(data.money.for_pay.value)}
              note="после удержаний WB"
            />
            <ExactStat
              label="Прибыль"
              value={formatMoneyCompact(data.money.profit.value)}
              note={formatPercent(data.money.margin_percent.value, 1)}
            />
          </div>
          <div className="space-y-3">
            <BreakdownRow
              label="Расходы WB"
              value={data.money.wb_expenses.value}
              total={Math.max(revenue, expenseTotal)}
              tone="amber"
            />
            <BreakdownRow
              label="Себестоимость и свои расходы"
              value={data.money.seller_expenses.value}
              total={Math.max(revenue, expenseTotal)}
              tone="sky"
            />
            <BreakdownRow
              label="Реклама"
              value={data.ads.spend.value}
              total={Math.max(revenue, expenseTotal)}
              tone="rose"
            />
            <BreakdownRow
              label="Чистая прибыль"
              value={data.money.profit.value}
              total={Math.max(revenue, expenseTotal)}
              tone="emerald"
            />
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-md">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Megaphone className="h-4 w-4 text-primary" />
            Эффективность рекламы
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-4 pt-0">
          <div className="grid gap-3 sm:grid-cols-4">
            <ExactStat
              label="Расход"
              value={formatMoneyCompact(data.ads.spend.value)}
              note="WB реклама"
            />
            <ExactStat
              label="ДРР"
              value={formatPercent(data.ads.drr_percent.value, 1)}
              note="расход / выручка"
            />
            <ExactStat
              label="Окупаемость"
              value={`${formatNumber(data.ads.roas.value)}x`}
              note="выручка / расход"
            />
            <ExactStat
              label="Цена клика"
              value={formatMoneyCompact(data.ads.cpc.value)}
              note="цена клика"
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <SmallStat
              label="Показы"
              value={formatNumber(data.ads.views.value)}
            />
            <SmallStat
              label="Клики"
              value={formatNumber(data.ads.clicks.value)}
            />
            <SmallStat
              label="Заказы"
              value={formatNumber(data.ads.orders.value)}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-md">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Warehouse className="h-4 w-4 text-primary" />
            Контроль склада
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 p-4 pt-0 sm:grid-cols-2 xl:grid-cols-4">
          <ExactStat
            label="Остаток"
            value={formatNumber(data.stock.stock_qty)}
            note="доступно"
          />
          <ExactStat
            label="Полный остаток"
            value={formatNumber(data.stock.full_stock_qty)}
            note="с учетом резервов"
          />
          <ExactStat
            label="Риск обнуления"
            value={formatNumber(data.stock.out_of_stock_risk)}
            note="карточек"
          />
          <ExactStat
            label="Дней запаса"
            value={formatNumber(data.stock.avg_days_of_stock)}
            note={
              data.stock.latest_date ? formatDate(data.stock.latest_date) : "—"
            }
          />
        </CardContent>
      </Card>

      <Card className="rounded-md">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Tags className="h-4 w-4 text-primary" />
            Контроль цен
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 p-4 pt-0 sm:grid-cols-2 xl:grid-cols-4">
          <ExactStat
            label="Цена до скидки"
            value={formatMoneyCompact(data.prices.avg_price)}
            note="средняя"
          />
          <ExactStat
            label="Цена после скидки"
            value={formatMoneyCompact(data.prices.avg_discounted_price)}
            note={formatPercent(data.prices.avg_discount_percent, 1)}
          />
          <ExactStat
            label="Плохая оборачиваемость"
            value={formatNumber(data.prices.bad_turnover)}
            note="по данным WB"
          />
          <ExactStat
            label="Карантин"
            value={formatNumber(data.prices.quarantine)}
            note="ценовые блокировки"
          />
        </CardContent>
      </Card>
    </div>
  );
}

function BreakdownRow({
  label,
  value,
  total,
  tone,
}: {
  label: string;
  value: number | null | undefined;
  total: number;
  tone: "emerald" | "sky" | "amber" | "rose";
}) {
  const numeric = Number(value || 0);
  const width =
    total > 0 ? Math.min(100, (Math.abs(numeric) / total) * 100) : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">
          {formatMoneyCompact(numeric)}
        </span>
      </div>
      <Progress
        value={width}
        className={cn("h-2 rounded-md", progressTone(tone))}
      />
    </div>
  );
}

function ProductsTable({
  rows,
  onSelect,
  onExport,
  exporting,
}: {
  rows: ProductRow[];
  onSelect: (row: ProductRow) => void;
  onExport: () => void;
  exporting: boolean;
}) {
  return (
    <Card className="rounded-md">
      <CardHeader className="p-4 pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <PackageSearch className="h-4 w-4 text-primary" />
            Карточки по воронке
          </CardTitle>
          <Button
            size="sm"
            variant="outline"
            onClick={onExport}
            disabled={exporting}
          >
            {exporting ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="mr-1.5 h-3.5 w-3.5" />
            )}
            Выгрузка
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Карточка</TableHead>
                <TableHead>Сигнал</TableHead>
                <TableHead className="text-right">Открытия</TableHead>
                <TableHead className="text-right">Корзина</TableHead>
                <TableHead className="text-right">Заказы</TableHead>
                <TableHead className="text-right">Выкуп</TableHead>
                <TableHead className="text-right">Выручка</TableHead>
                <TableHead className="text-right">Прибыль</TableHead>
                <TableHead className="text-right">Реклама</TableHead>
                <TableHead className="text-right">Остаток</TableHead>
                <TableHead className="text-right">Цена</TableHead>
                <TableHead>Следующий шаг</TableHead>
                <TableHead className="w-[64px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  key={row.nm_id}
                  className="cursor-pointer"
                  onClick={() => onSelect(row)}
                >
                  <TableCell className="min-w-[260px]">
                    <div className="font-medium">
                      {row.vendor_code || row.nm_id}
                    </div>
                    <div className="line-clamp-1 text-xs text-muted-foreground">
                      {row.title || "—"}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
                      <span className="font-mono">{row.nm_id}</span>
                      {row.brand_name && <span>{row.brand_name}</span>}
                      {row.subject_name && <span>{row.subject_name}</span>}
                      <Badge
                        variant="outline"
                        className="h-5 rounded-md px-1.5"
                      >
                        {row.row_source === "money" ? "деньги" : "воронка"}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell className="min-w-[170px]">
                    <StatusBadge status={row.status} />
                    {row.issue && (
                      <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                        {row.issue}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatNumber(row.open_count)}
                    <DeltaMini value={row.open_delta_percent} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <div>{formatNumber(row.cart_count)}</div>
                    <div className="text-xs text-muted-foreground">
                      {formatPercent(row.cart_rate, 1)}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <div>{formatNumber(row.order_count)}</div>
                    <DeltaMini value={row.order_delta_percent} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatPercent(row.buyout_rate, 1)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMoneyCompact(row.revenue)}
                    <DeltaMini value={row.revenue_delta_percent} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <div
                      className={cn(
                        (row.profit ?? 0) < 0
                          ? "text-red-700 dark:text-red-300"
                          : "text-emerald-700 dark:text-emerald-300",
                      )}
                    >
                      {formatMoneyCompact(row.profit)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {formatPercent(row.margin_percent, 1)}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <div>{formatMoneyCompact(row.ad_spend)}</div>
                    <div className="text-xs text-muted-foreground">
                      {formatPercent(row.drr_percent, 1)}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <div>{formatNumber(row.stock_qty)}</div>
                    <div className="text-xs text-muted-foreground">
                      {row.days_of_stock == null
                        ? "—"
                        : `${formatNumber(row.days_of_stock)} дн.`}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <div>
                      {formatMoneyCompact(row.current_discounted_price)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {formatMoneyCompact(row.current_price)}
                    </div>
                  </TableCell>
                  <TableCell className="min-w-[260px] text-xs text-muted-foreground">
                    {row.action || "—"}
                  </TableCell>
                  <TableCell>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-8 w-8 p-0"
                      onClick={(event) => {
                        event.stopPropagation();
                        onSelect(row);
                      }}
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={13}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    Нет данных
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function RegionsPanel({
  rows,
  onSelect,
  onExport,
  exporting,
}: {
  rows: RegionRow[];
  onSelect: (row: RegionRow) => void;
  onExport: () => void;
  exporting: boolean;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(420px,0.9fr)]">
      <Card className="rounded-md">
        <CardHeader className="p-4 pb-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <BarChart3 className="h-4 w-4 text-primary" />
              Региональная выручка
            </CardTitle>
            <Button
              size="sm"
              variant="outline"
              onClick={onExport}
              disabled={exporting}
            >
              {exporting ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="mr-1.5 h-3.5 w-3.5" />
              )}
              Выгрузка
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <div className="h-[360px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={rows.slice(0, 12)}
                layout="vertical"
                margin={{ top: 8, right: 22, left: 18, bottom: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--border)"
                  horizontal={false}
                />
                <XAxis
                  type="number"
                  tickFormatter={(value) => formatMoneyCompact(Number(value))}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  dataKey={(row: RegionRow) =>
                    row.region_name || row.country_name || "—"
                  }
                  type="category"
                  tickLine={false}
                  axisLine={false}
                  width={112}
                />
                <RechartsTooltip content={<RegionTooltip />} />
                <Bar dataKey="revenue" radius={[0, 4, 4, 0]}>
                  {rows.slice(0, 12).map((_, index) => (
                    <Cell
                      key={index}
                      fill={
                        index === 0 ? chartColors.revenue : chartColors.open
                      }
                      fillOpacity={index === 0 ? 0.9 : 0.68}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-md">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-sm">Регионы по выручке</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Регион</TableHead>
                  <TableHead className="text-right">Выручка</TableHead>
                  <TableHead className="text-right">Шт</TableHead>
                  <TableHead className="text-right">Доля</TableHead>
                  <TableHead className="w-[64px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row, index) => (
                  <TableRow
                    key={`${row.country_name}-${row.region_name}-${row.city_name}-${index}`}
                    className="cursor-pointer"
                    onClick={() => onSelect(row)}
                  >
                    <TableCell>
                      <div className="font-medium">
                        {row.region_name || row.country_name || "—"}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {[row.city_name, row.federal_district]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMoneyCompact(row.revenue)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatNumber(row.units_sold)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatPercent(row.share_percent, 1)}
                    </TableCell>
                    <TableCell>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0"
                        onClick={(event) => {
                          event.stopPropagation();
                          onSelect(row);
                        }}
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {rows.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="py-10 text-center text-sm text-muted-foreground"
                    >
                      Нет данных
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function InsightsPanel({ data }: { data: AnalyticsOverview }) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(380px,0.8fr)]">
      <Card className="rounded-md">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <AlertTriangle className="h-4 w-4 text-primary" />
            Сигналы
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-4 pt-0">
          {data.recommendations.length ? (
            data.recommendations.map((item, index) => (
              <div
                key={`${item.title}-${index}`}
                className="rounded-md border p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge severity={item.severity} />
                  <div className="font-medium">{item.title}</div>
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  {item.detail}
                </div>
                <div className="mt-2 text-sm">{item.action}</div>
              </div>
            ))
          ) : (
            <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
              Критичных сигналов нет
            </div>
          )}
        </CardContent>
      </Card>

      <DataSourcesPanel sources={data.data_sources} />
    </div>
  );
}

function DataSourcesPanel({ sources }: { sources: DataSourceStatus[] }) {
  return (
    <Card className="rounded-md">
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Database className="h-4 w-4 text-primary" />
          Состояние данных
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-0">
        {sources.map((source) => (
          <div key={source.key} className="rounded-md border p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-medium">{source.label}</div>
                <div className="truncate text-xs text-muted-foreground">
                  {source.note || "—"}
                </div>
              </div>
              <StatusBadge
                status={source.status === "ok" ? "ok" : "watch"}
                label={statusLabel(source.status)}
              />
            </div>
            <div className="mt-2 text-sm tabular-nums text-muted-foreground">
              {formatNumber(source.rows)} строк
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function RawDataTabs({
  extraQuery,
}: {
  extraQuery: Record<string, string | number | undefined>;
}) {
  const rawKey = JSON.stringify(extraQuery);
  return (
    <Tabs defaultValue="funnel" className="space-y-3">
      <TabsList className="rounded-md">
        <TabsTrigger value="funnel">Строки воронки</TabsTrigger>
        <TabsTrigger value="regions">Строки регионов</TabsTrigger>
      </TabsList>
      <TabsContent value="funnel">
        <DataBrowser
          path="/analytics/funnel"
          columns={funnelCols}
          extraQuery={extraQuery}
          queryKey={`analytics-raw-funnel-${rawKey}`}
        />
      </TabsContent>
      <TabsContent value="regions">
        <DataBrowser
          path="/analytics/regions"
          columns={regionCols}
          extraQuery={extraQuery}
          queryKey={`analytics-raw-regions-${rawKey}`}
        />
      </TabsContent>
    </Tabs>
  );
}

function ApiCoveragePanel({ data }: { data: AnalyticsOverview }) {
  return (
    <Card className="rounded-md">
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Boxes className="h-4 w-4 text-primary" />
          Покрытие интеграций WB
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.api_capabilities.map((item) => (
            <div key={item.key} className="rounded-md border p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-medium">{item.label}</div>
                  <div className="mt-1 truncate font-mono text-[11px] text-muted-foreground">
                    {item.endpoint}
                  </div>
                </div>
                <StatusBadge
                  status={
                    item.status === "active" || item.status === "active_sync"
                      ? "ok"
                      : "watch"
                  }
                  label={statusLabel(item.status)}
                />
              </div>
              {item.note && (
                <div className="mt-2 text-xs text-muted-foreground">
                  {item.note}
                </div>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function AnalyticsSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <Skeleton key={index} className="h-28 rounded-md" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(360px,0.85fr)]">
        <Skeleton className="h-[430px] rounded-md" />
        <Skeleton className="h-[430px] rounded-md" />
      </div>
      <Skeleton className="h-[360px] rounded-md" />
    </div>
  );
}

function queryForTarget(
  target: DrillTarget,
): Record<string, string | number | undefined> {
  if (target.kind === "product") return { nm_id: target.nmId };
  if (target.kind === "region") {
    return {
      region_name: target.regionName || undefined,
      country_name: target.countryName || undefined,
    };
  }
  if (target.kind === "day")
    return { date_from: target.date, date_to: target.date };
  return {};
}

function drillTitle(target: DrillTarget, data: AnalyticsOverview): string {
  if (target.kind === "metric") {
    return (
      buildMetricDefinitions(data).find((item) => item.key === target.key)
        ?.title ?? "Показатель"
    );
  }
  if (target.kind === "product") {
    const row = data.products.find((item) => item.nm_id === target.nmId);
    return row?.vendor_code || String(target.nmId);
  }
  if (target.kind === "region") {
    return target.regionName || target.countryName || "Регион";
  }
  return formatDate(target.date);
}

function drillSubtitle(target: DrillTarget, data: AnalyticsOverview): string {
  if (target.kind === "metric") {
    return (
      buildMetricDefinitions(data).find((item) => item.key === target.key)
        ?.subtitle ?? "Точный показатель"
    );
  }
  if (target.kind === "product") {
    const row = data.products.find((item) => item.nm_id === target.nmId);
    return [
      row?.title,
      row?.brand_name,
      row?.subject_name,
      `nm_id ${target.nmId}`,
    ]
      .filter(Boolean)
      .join(" · ");
  }
  if (target.kind === "region") {
    return [target.countryName, "пересчёт по выбранному региону"]
      .filter(Boolean)
      .join(" · ");
  }
  return "Детализация за один день";
}

function drillKindTitle(target: DrillTarget): string {
  switch (target.kind) {
    case "metric":
      return "Выбранный показатель";
    case "product":
      return "Карточка товара";
    case "region":
      return "Регион продаж";
    case "day":
      return "Один день";
  }
}

function metricValueForTrend(key: MetricKey, row: TrendPoint): number | null {
  switch (key) {
    case "revenue":
      return row.revenue;
    case "profit":
      return row.profit;
    case "ad_spend":
      return row.ad_spend;
    case "stock_qty":
      return row.stock_qty;
    case "order_count":
      return row.order_count;
    case "cart_rate":
      return row.cart_rate;
    case "order_rate":
      return row.order_rate;
    case "buyout_rate":
      return row.buyout_rate;
    case "hidden":
      return null;
  }
}

function formatMetricExact(
  key: MetricKey,
  value: number | null | undefined,
): string {
  if (key === "revenue" || key === "profit" || key === "ad_spend") {
    return formatMoney(value);
  }
  if (key === "cart_rate" || key === "order_rate" || key === "buyout_rate") {
    return formatPercent(value, 2);
  }
  return formatNumber(value);
}

type FunnelStage = {
  key: string;
  label: string;
  value: number;
  rate: number | null;
  width: number;
  note: string;
  colorClass: string;
};

function buildFunnelStages(data?: AnalyticsOverview): FunnelStage[] {
  const s = data?.summary;
  const open = s?.open_count.value || 0;
  const cart = s?.cart_count.value || 0;
  const orders = s?.order_count.value || 0;
  const buyout = s?.buyout_count.value || 0;
  return [
    {
      key: "open",
      label: "Открытия",
      value: open,
      rate: null,
      width: 100,
      note: "верх воронки",
      colorClass: "[&>div]:bg-chart-1",
    },
    {
      key: "cart",
      label: "Корзина",
      value: cart,
      rate: s?.cart_rate.value ?? null,
      width: percentWidth(cart, open),
      note: "открытие → корзина",
      colorClass: "[&>div]:bg-chart-2",
    },
    {
      key: "orders",
      label: "Заказы",
      value: orders,
      rate: s?.order_rate.value ?? null,
      width: percentWidth(orders, cart),
      note: "корзина → заказ",
      colorClass: "[&>div]:bg-chart-3",
    },
    {
      key: "buyout",
      label: "Выкупы",
      value: buyout,
      rate: s?.buyout_rate.value ?? null,
      width: percentWidth(buyout, orders),
      note: "заказ → выкуп",
      colorClass: "[&>div]:bg-chart-5",
    },
  ];
}

function percentWidth(value: number, total: number) {
  if (!total) return 0;
  return Math.max(2, Math.min(100, (value / total) * 100));
}

function SmallStat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-md border bg-card px-3 py-2.5 shadow-sm">
      <div className="text-[11px] font-medium uppercase text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 break-words text-base font-semibold tabular-nums">
        {value}
      </div>
    </div>
  );
}

function DeltaLine({ metric }: { metric: ComparisonMetric }) {
  if (metric.delta_percent == null) {
    return (
      <div className="mt-3 text-xs text-muted-foreground">
        Нет прошлого периода
      </div>
    );
  }
  const positive = metric.delta_percent >= 0;
  const Icon = positive ? TrendingUp : TrendingDown;
  return (
    <div
      className={cn(
        "mt-3 flex items-center gap-1 text-xs tabular-nums",
        positive
          ? "text-emerald-700 dark:text-emerald-300"
          : "text-red-700 dark:text-red-300",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {positive ? "+" : ""}
      {formatPercent(metric.delta_percent, 1)}
    </div>
  );
}

function DeltaMini({ value }: { value?: number | null }) {
  if (value == null)
    return <div className="text-[11px] text-muted-foreground">—</div>;
  const positive = value >= 0;
  return (
    <div
      className={cn(
        "text-[11px] tabular-nums",
        positive
          ? "text-emerald-700 dark:text-emerald-300"
          : "text-red-700 dark:text-red-300",
      )}
    >
      {positive ? "+" : ""}
      {formatPercent(value, 1)}
    </div>
  );
}

function StatusBadge({ status, label }: { status: string; label?: string }) {
  const normalized = status === "empty" ? "watch" : status;
  return (
    <Badge
      variant="outline"
      className={cn("rounded-md", statusClass(normalized))}
    >
      {label ?? statusLabel(status)}
    </Badge>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <StatusBadge
      status={severity === "info" ? "watch" : severity}
      label={statusLabel(severity)}
    />
  );
}

function statusLabel(status: string) {
  switch (status) {
    case "ok":
      return "Норма";
    case "watch":
      return "Проверить";
    case "warning":
      return "Внимание";
    case "danger":
      return "Критично";
    case "info":
      return "Информация";
    case "active":
      return "Работает";
    case "active_sync":
      return "Синхронизируется";
    case "candidate":
      return "Запланировано";
    case "empty":
      return "Нет данных";
    default:
      return status;
  }
}

function statusClass(status: string) {
  switch (status) {
    case "ok":
      return "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200";
    case "danger":
      return "border-red-200 bg-red-50 text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200";
    case "warning":
      return "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200";
    default:
      return "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-200";
  }
}

function toneBorder(tone: "good" | "warning" | "danger" | "neutral") {
  switch (tone) {
    case "good":
      return "border-emerald-200/80";
    case "warning":
      return "border-amber-200/80";
    case "danger":
      return "border-red-200/80";
    default:
      return "";
  }
}

function toneIcon(tone: "good" | "warning" | "danger" | "neutral") {
  switch (tone) {
    case "good":
      return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300";
    case "warning":
      return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300";
    case "danger":
      return "border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300";
    default:
      return "border-border bg-muted/50 text-muted-foreground";
  }
}

function domainTone(tone: "emerald" | "sky" | "amber" | "rose") {
  switch (tone) {
    case "emerald":
      return "border-l-emerald-500";
    case "amber":
      return "border-l-amber-500";
    case "rose":
      return "border-l-rose-500";
    default:
      return "border-l-sky-500";
  }
}

function domainIconTone(tone: "emerald" | "sky" | "amber" | "rose") {
  switch (tone) {
    case "emerald":
      return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300";
    case "amber":
      return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300";
    case "rose":
      return "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300";
    default:
      return "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300";
  }
}

function progressTone(tone: "emerald" | "sky" | "amber" | "rose") {
  switch (tone) {
    case "emerald":
      return "[&>div]:bg-emerald-500";
    case "amber":
      return "[&>div]:bg-amber-500";
    case "rose":
      return "[&>div]:bg-rose-500";
    default:
      return "[&>div]:bg-sky-500";
  }
}

function rateTone(
  value: number | null | undefined,
  warning: number,
  good: number,
): "good" | "warning" | "danger" | "neutral" {
  if (value == null) return "neutral";
  if (value >= good) return "good";
  if (value >= warning) return "warning";
  return "danger";
}

function shortDate(value: string) {
  try {
    return new Date(value).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
    });
  } catch {
    return value;
  }
}

function TrendTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload as TrendPoint | undefined;
  return (
    <div className="rounded-md border bg-background px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium">{shortDate(label)}</div>
      <div className="grid gap-1">
        <TooltipRow label="Открытия" value={formatNumber(point?.open_count)} />
        <TooltipRow label="Корзина" value={formatNumber(point?.cart_count)} />
        <TooltipRow label="Заказы" value={formatNumber(point?.order_count)} />
        <TooltipRow
          label="Выручка"
          value={formatMoneyCompact(point?.revenue)}
        />
        <TooltipRow label="Прибыль" value={formatMoneyCompact(point?.profit)} />
        <TooltipRow
          label="Реклама"
          value={formatMoneyCompact(point?.ad_spend)}
        />
      </div>
    </div>
  );
}

function RegionTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as RegionRow | undefined;
  return (
    <div className="rounded-md border bg-background px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium">
        {row?.region_name || row?.country_name || "—"}
      </div>
      <TooltipRow label="Выручка" value={formatMoneyCompact(row?.revenue)} />
      <TooltipRow label="Шт" value={formatNumber(row?.units_sold)} />
      <TooltipRow label="Доля" value={formatPercent(row?.share_percent, 1)} />
    </div>
  );
}

function TooltipRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex min-w-[150px] items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  );
}
