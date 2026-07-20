// @ts-nocheck
import { createFileRoute, Link } from "@tanstack/react-router";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, useEffect } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Ban,
  BarChart3,
  Boxes,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock,
  Eye,
  ImageOff,
  Info,
  Layers,
  ListFilter,
  MapPin,
  Minus,
  Package,
  RefreshCw,
  Ruler,
  Search,
  ShieldCheck,
  ShoppingCart,
  SlidersHorizontal,
  TrendingDown,
  TrendingUp,
  Wallet,
  Wrench,
  X,
} from "lucide-react";

import { PageHeader, PageShell } from "@/components/PageShell";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { EndpointError } from "@/components/EndpointError";
import { TrustStatusBanner, trustInputsFromSummary } from "@/components/money-ui/TrustStatusBanner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";
import { formatMoney, formatNumber, formatPercent } from "@/lib/format";
import { fetchMoneySummary, fetchPurchasePlan } from "@/lib/money-endpoints";

export const Route = createFileRoute("/_authenticated/purchase-plan")({
  component: PurchasePlanPage,
  errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} />,
});

const STATUS_META: Record<string, any> = {
  REORDER: {
    label: "Нужно закупить",
    short: "Закупка",
    icon: ShoppingCart,
    tone: "border-emerald-300 bg-emerald-50 text-emerald-800",
    card: "border-emerald-200 bg-emerald-50/30 hover:border-emerald-400",
    accent: "bg-emerald-500",
    dot: "bg-emerald-500",
  },
  LIQUIDATE: {
    label: "Разгрузить остаток",
    short: "Излишек",
    icon: TrendingDown,
    tone: "border-amber-300 bg-amber-50 text-amber-900",
    card: "border-amber-200 bg-amber-50/25 hover:border-amber-400",
    accent: "bg-amber-500",
    dot: "bg-amber-500",
  },
  DO_NOT_BUY: {
    label: "Не покупать",
    short: "Стоп",
    icon: Ban,
    tone: "border-rose-300 bg-rose-50 text-rose-800",
    card: "border-rose-200 bg-rose-50/25 hover:border-rose-400",
    accent: "bg-rose-500",
    dot: "bg-rose-500",
  },
  DO_NOT_REORDER: {
    label: "Не покупать",
    short: "Стоп",
    icon: Ban,
    tone: "border-rose-300 bg-rose-50 text-rose-800",
    card: "border-rose-200 bg-rose-50/25 hover:border-rose-400",
    accent: "bg-rose-500",
    dot: "bg-rose-500",
  },
  WAIT_DATA: {
    label: "Нужны данные",
    short: "Данные",
    icon: AlertTriangle,
    tone: "border-cyan-300 bg-cyan-50 text-cyan-800",
    card: "border-cyan-200 bg-cyan-50/25 hover:border-cyan-400",
    accent: "bg-cyan-500",
    dot: "bg-slate-500",
  },
  PROTECT_STOCK: {
    label: "Дождаться поставки",
    short: "В пути",
    icon: ShieldCheck,
    tone: "border-cyan-300 bg-cyan-50 text-cyan-800",
    card: "border-blue-200 bg-blue-50/25 hover:border-blue-400",
    accent: "bg-blue-500",
    dot: "bg-cyan-500",
  },
  WATCH: {
    label: "Достаточно",
    short: "Контроль",
    icon: Eye,
    tone: "border-blue-300 bg-blue-50 text-blue-800",
    card: "border-slate-200 bg-background hover:border-blue-300",
    accent: "bg-blue-500",
    dot: "bg-blue-500",
  },
};

const FILTERS = [
  { key: "actionable", label: "Решить сейчас", icon: ListFilter, tone: "text-slate-700" },
  { key: "REORDER", label: "Закупить", icon: ShoppingCart, tone: "text-emerald-700" },
  { key: "LIQUIDATE", label: "Излишки", icon: TrendingDown, tone: "text-amber-700" },
  { key: "DO_NOT_BUY", label: "Стоп", icon: Ban, tone: "text-rose-700" },
  { key: "WAIT_DATA", label: "Данные", icon: AlertTriangle, tone: "text-cyan-700" },
  { key: "all", label: "Все товары", icon: Package, tone: "text-slate-700" },
];

const PROFIT_FILTERS = [
  { value: "all", label: "Любая прибыль" },
  { value: "profitable", label: "Только в плюсе" },
  { value: "loss", label: "Только в минусе" },
  { value: "unknown", label: "Прибыль не рассчитана" },
];

const DATA_FILTERS = [
  { value: "all", label: "Любые данные" },
  { value: "final", label: "Только финальные" },
  { value: "estimated", label: "Расчетные без блокеров" },
  { value: "missing", label: "Есть блокеры данных" },
];

const STOCK_FILTERS = [
  { value: "all", label: "Любые остатки" },
  { value: "low", label: "Низкий запас" },
  { value: "overstock", label: "Излишки" },
  { value: "out", label: "Нулевой остаток" },
  { value: "in_transit", label: "Есть товар в пути" },
];

const GROUP_OPTIONS = [
  { value: "article", label: "По артикулу WB" },
  { value: "sku", label: "По SKU / размеру" },
];

const DEFAULT_SORT_KEY = "priority:desc";

function PurchasePlanPage() {
  const { activeId } = useAccounts();
  const { from: dateFrom, to: dateTo } = useDateRange();
  const qc = useQueryClient();

  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("actionable");
  const [profitFilter, setProfitFilter] = useState("all");
  const [dataFilter, setDataFilter] = useState("all");
  const [stockFilter, setStockFilter] = useState("all");
  const [sortKey, setSortKey] = useState(DEFAULT_SORT_KEY);
  const [groupBy, setGroupBy] = useState<"article" | "sku">("article");
  const [selected, setSelected] = useState<any | null>(null);

  useEffect(() => {
    setOffset(0);
  }, [activeId, dateFrom, dateTo, limit, filter, search, profitFilter, dataFilter, stockFilter, sortKey, groupBy]);

  const [sortBy, sortDir] = sortKey.split(":") as [string, "asc" | "desc"];
  const activeAdvancedFilters =
    profitFilter !== "all" ||
    dataFilter !== "all" ||
    stockFilter !== "all" ||
    groupBy !== "article" ||
    !!search.trim();
  const activeFilterCount =
    Number(profitFilter !== "all") +
    Number(dataFilter !== "all") +
    Number(stockFilter !== "all") +
    Number(groupBy !== "article") +
    Number(!!search.trim());

  const purchaseQ = useQuery({
    queryKey: [
      "purchase-plan",
      activeId,
      dateFrom,
      dateTo,
      limit,
      offset,
      filter,
      search,
      profitFilter,
      dataFilter,
      stockFilter,
      sortKey,
      groupBy,
    ],
    enabled: !!activeId,
    queryFn: () =>
      fetchPurchasePlan({
        accountId: activeId!,
        dateFrom,
        dateTo,
        limit,
        offset,
        groupBy,
        includeBlocked: true,
        sortBy,
        sortDir,
        statusFilter: filter,
        search: search.trim() || undefined,
        profitFilter,
        dataFilter,
        stockFilter,
      }) as Promise<any>,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const moneyQ = useQuery({
    queryKey: ["money-summary-purchase", activeId, dateFrom, dateTo],
    enabled: !!activeId,
    queryFn: () => fetchMoneySummary({ accountId: activeId!, dateFrom, dateTo } as any) as Promise<any>,
    retry: false,
    staleTime: 60_000,
  });

  const data = purchaseQ.data;
  const items = useMemo(() => extractItems(data), [data]);
  const summary = (data?.summary ?? {}) as any;

  const stats = useMemo(() => buildStats(items, summary), [items, summary]);
  const filtered = items;
  const filteredTotal = Number(data?.total ?? filtered.length);
  const trustInputs = moneyQ.data ? trustInputsFromSummary(moneyQ.data) : null;

  return (
    <PageShell>
      <PageHeader
        title="План закупок"
        description="Что докупить, где остановить закупку и в каких остатках заморожены деньги."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              qc.invalidateQueries({
                predicate: (q) =>
                  String(q.queryKey[0]).startsWith("purchase-") ||
                  q.queryKey[0] === "money-summary-purchase",
              })
            }
            disabled={purchaseQ.isFetching}
          >
            <RefreshCw className={`mr-1.5 h-4 w-4 ${purchaseQ.isFetching ? "animate-spin" : ""}`} />
            Обновить
          </Button>
        }
      />

      {activeId && (
        <DataDependencyNotice
          accountId={activeId}
          domains={["stocks", "sales", "orders", "finance", "product_cards", "supplies"]}
        />
      )}

      {trustInputs && (
        <TrustStatusBanner trust={trustInputs.trust} quality={trustInputs.quality} className="mb-3" />
      )}

      {!activeId && (
        <Alert className="mb-3">
          <AlertTitle>Кабинет не выбран</AlertTitle>
          <AlertDescription>Выберите кабинет в верхней панели.</AlertDescription>
        </Alert>
      )}

      {purchaseQ.isError && (
        <Alert variant="destructive" className="mb-3">
          <AlertTitle>План закупок не загрузился</AlertTitle>
          <AlertDescription>
            <Button size="sm" onClick={() => purchaseQ.refetch()} disabled={purchaseQ.isFetching}>
              Повторить
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {purchaseQ.isLoading && <LoadingState />}

      {data && (
        <div className="space-y-4">
          <SummaryGrid stats={stats} />

          {stats.waitData > 0 && stats.reorder === 0 && (
            <Alert className="border-amber-300 bg-amber-50 text-amber-950">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Сначала нужно закрыть блокеры данных</AlertTitle>
              <AlertDescription>
                По {formatNumber(stats.waitData)} товарам не хватает финансов, себестоимости, остатков или истории продаж.
              </AlertDescription>
            </Alert>
          )}

          <section className="overflow-hidden rounded-lg border bg-background shadow-sm">
            <div className="space-y-3 border-b bg-muted/10 p-3">
              <div className="flex flex-col gap-3 2xl:flex-row 2xl:items-center 2xl:justify-between">
                <Tabs value={filter} onValueChange={setFilter} className="w-full 2xl:max-w-3xl">
                  <TabsList className="grid h-9 w-full grid-cols-2 gap-1 bg-muted/60 p-1 sm:grid-cols-3 xl:grid-cols-6">
                    {FILTERS.map((item) => {
                      const FilterIcon = item.icon;
                      return (
                        <TabsTrigger
                          key={item.key}
                          value={item.key}
                          className="h-7 min-w-0 justify-center gap-1.5 rounded-md px-2 text-[11px] font-medium data-[state=active]:bg-background data-[state=active]:shadow-sm"
                        >
                          <FilterIcon className={`h-3.5 w-3.5 shrink-0 ${item.tone}`} />
                          <span className="truncate">{item.label}</span>
                          <span className="rounded bg-muted px-1 text-[10px] tabular-nums text-muted-foreground">
                            {filterCount(item.key, stats)}
                          </span>
                        </TabsTrigger>
                      );
                    })}
                  </TabsList>
                </Tabs>

                <div className="relative w-full 2xl:w-[360px]">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="nm_id, название, артикул продавца"
                    className="h-9 rounded-md bg-background pl-8 pr-8 text-xs"
                  />
                  {search && (
                    <button
                      type="button"
                      onClick={() => setSearch("")}
                      className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition hover:bg-muted hover:text-foreground"
                      aria-label="Очистить поиск"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <FilterPopover
                  activeCount={activeFilterCount}
                  profitFilter={profitFilter}
                  setProfitFilter={setProfitFilter}
                  dataFilter={dataFilter}
                  setDataFilter={setDataFilter}
                  stockFilter={stockFilter}
                  setStockFilter={setStockFilter}
                  groupBy={groupBy}
                  setGroupBy={setGroupBy}
                  onReset={() => {
                    setSearch("");
                    setProfitFilter("all");
                    setDataFilter("all");
                    setStockFilter("all");
                    setGroupBy("article");
                  }}
                />
                {activeAdvancedFilters && (
                  <div className="flex flex-wrap gap-1.5">
                    {search.trim() && <ActiveFilterChip label={`Поиск: ${search.trim()}`} onClear={() => setSearch("")} />}
                    {profitFilter !== "all" && <ActiveFilterChip label={optionLabel(PROFIT_FILTERS, profitFilter)} onClear={() => setProfitFilter("all")} />}
                    {dataFilter !== "all" && <ActiveFilterChip label={optionLabel(DATA_FILTERS, dataFilter)} onClear={() => setDataFilter("all")} />}
                    {stockFilter !== "all" && <ActiveFilterChip label={optionLabel(STOCK_FILTERS, stockFilter)} onClear={() => setStockFilter("all")} />}
                    {groupBy !== "article" && <ActiveFilterChip label={optionLabel(GROUP_OPTIONS, groupBy)} onClear={() => setGroupBy("article")} />}
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center justify-between border-b bg-background px-3 py-2">
              <div className="flex items-center gap-2">
                <ListFilter className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs font-medium">Товары</span>
                <span className="text-[11px] text-muted-foreground">
                  {formatNumber(filteredTotal)} из {formatNumber(stats.total)}
                </span>
                {sortKey !== DEFAULT_SORT_KEY && (
                  <ActiveFilterChip label={`Сорт: ${sortLabel(sortKey)}`} onClear={() => setSortKey(DEFAULT_SORT_KEY)} />
                )}
              </div>
              {purchaseQ.isFetching && (
                <span className="text-[11px] text-muted-foreground">Обновление...</span>
              )}
            </div>

            <div className="md:hidden">
              <div className="divide-y">
                {filtered.map((item: any) => (
                  <MobilePurchaseCard
                    key={rowKey(item)}
                    item={item}
                    onOpen={() => setSelected(item)}
                  />
                ))}
              </div>
            </div>

            <div className="hidden overflow-x-auto md:block">
              <div className="min-w-[1180px]">
                <PurchaseListHeader sortKey={sortKey} onSort={setSortKey} />
                <div className="divide-y">
                  {filtered.map((item: any) => (
                    <ProductDecisionCard key={rowKey(item)} item={item} onOpen={() => setSelected(item)} />
                  ))}
                </div>
              </div>
              {!filtered.length && (
                <div className="flex min-h-52 flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-muted/20 p-8 text-center">
                  <Package className="h-8 w-8 text-muted-foreground" />
                  <div className="text-sm font-medium">В этом фильтре товаров нет</div>
                  <div className="text-xs text-muted-foreground">Измените фильтр или строку поиска.</div>
                </div>
              )}
            </div>
          </section>

          <PaginationBar
            limit={limit}
            offset={offset}
            shown={filtered.length}
            pageItems={items.length}
            total={filteredTotal}
            isFetching={purchaseQ.isFetching}
            onLimit={(value) => {
              setLimit(value);
              setOffset(0);
            }}
            onPrev={() => setOffset(Math.max(0, offset - limit))}
            onNext={() => setOffset(offset + limit)}
          />
        </div>
      )}

      <ProductDetailSheet item={selected} open={!!selected} onOpenChange={(open) => !open && setSelected(null)} />
    </PageShell>
  );
}

function MobilePurchaseCard({ item, onOpen }: { item: any; onOpen: () => void }) {
  const meta = statusMeta(item.status);
  const Icon = meta.icon;
  const trend = trendMeta(item);
  const coverage = coveragePercent(item);
  const recommended = recommendText(item);
  const unitProfit = num(item.net_profit_per_unit);
  const unitProfitTone =
    item.net_profit_per_unit == null
      ? "neutral"
      : unitProfit >= 0
        ? "success"
        : "danger";
  const stockValue = num(item.stock_value ?? item.frozen_cash);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="relative w-full bg-background p-3 text-left transition hover:bg-muted/30"
    >
      <span className={`absolute inset-y-3 left-0 w-0.5 ${meta.accent}`} />
      <div className="flex gap-3">
        <ProductImage item={item} className="h-[72px] w-[58px] shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <span
              className={`inline-flex h-5 max-w-full items-center gap-1 rounded px-1.5 text-[10px] font-medium ${meta.tone}`}
            >
              <Icon className="h-3 w-3 shrink-0" />
              <span className="truncate">{meta.short}</span>
            </span>
            {item.financial_final === false ? (
              <span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                расчет
              </span>
            ) : null}
          </div>
          <div className="line-clamp-2 text-sm font-semibold leading-snug">
            {item.title ?? item.name ?? item.vendor_code ?? "Товар"}
          </div>
          <div className="mt-1 flex min-w-0 flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
            <span>nm {item.nm_id ?? "—"}</span>
            <span className="truncate">
              {item.vendor_code ?? item.barcode ?? "без артикула"}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <MobileMetric label="Остаток" value={formatNumber(num(item.available_stock))} />
        <MobileMetric
          label="Продажи 30д"
          value={formatNumber(num(item.sales_30d))}
          sub={`${formatDecimal(num(item.sales_velocity_daily), 1)} шт/день`}
        />
        <MobileMetric label="Динамика" value={trend.label} sub={trend.sub} tone={trend.tone} />
        <MobileMetric label="В остатке" value={formatMoney(stockValue)} />
        <MobileMetric label="Закупка" value={recommended} sub={coverage.label} progress={coverage.value} />
        <MobileMetric
          label="1 шт."
          value={formatSignedMoney(item.net_profit_per_unit)}
          sub={profitabilityText(item)}
          tone={unitProfitTone}
        />
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 rounded-md bg-muted/35 px-2.5 py-2">
        <div className="min-w-0 text-xs text-muted-foreground">
          {item.next_step || meta.label}
        </div>
        <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary">
          Открыть
          <ArrowRight className="h-3.5 w-3.5" />
        </span>
      </div>
    </button>
  );
}

function MobileMetric({ label, value, sub, tone, progress }: any) {
  const toneClass =
    tone === "danger"
      ? "text-rose-700"
      : tone === "success"
        ? "text-emerald-700"
        : tone === "warning"
          ? "text-amber-700"
          : "text-foreground";
  return (
    <div className="min-w-0 rounded-md border bg-card px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className={`mt-0.5 truncate text-sm font-semibold tabular-nums ${toneClass}`}>
        {value}
      </div>
      {progress != null ? (
        <Progress value={progress} className="mt-1.5 h-1" />
      ) : null}
      {sub ? (
        <div className="mt-1 truncate text-[10px] leading-3 text-muted-foreground">
          {sub}
        </div>
      ) : null}
    </div>
  );
}

function PurchaseListHeader({ sortKey, onSort }: { sortKey: string; onSort: (value: string) => void }) {
  const headers = [
    { label: "", className: "" },
    { label: "Товар", className: "" },
    { label: "Остаток", icon: Boxes, sort: "available_stock" },
    { label: "Продажи", icon: Activity, sort: "sales_30d" },
    { label: "Динамика", icon: TrendingUp, sort: "trend" },
    { label: "В остатке", icon: Wallet, sort: "stock_value" },
    { label: "Закупка", icon: ShoppingCart, sort: "recommended_qty" },
    { label: "1 шт.", icon: CheckCircle2, sort: "unit_profit" },
    { label: "", className: "text-right" },
  ];
  const [activeField, activeDir] = String(sortKey || DEFAULT_SORT_KEY).split(":");

  const toggleSort = (field: string) => {
    const nextDir = activeField === field && activeDir === "desc" ? "asc" : "desc";
    onSort(`${field}:${nextDir}`);
  };

  return (
    <div className="sticky top-0 z-[1] grid grid-cols-[68px_minmax(240px,1.25fr)_92px_100px_92px_118px_112px_100px_72px] gap-3 border-b bg-muted/35 px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
      {headers.map((header, index) => {
        const HeaderIcon = header.icon;
        const isActive = header.sort && activeField === header.sort;
        const SortIcon = isActive ? (activeDir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
        return (
          <div key={`${header.label}-${index}`} className={`flex min-w-0 items-center gap-1 ${header.className ?? ""}`}>
            {HeaderIcon && <HeaderIcon className="h-3 w-3 shrink-0" />}
            <span className="truncate">{header.label}</span>
            {header.sort && (
              <button
                type="button"
                onClick={() => toggleSort(header.sort)}
                className={`ml-0.5 inline-flex h-5 w-5 items-center justify-center rounded text-muted-foreground transition hover:bg-background hover:text-foreground ${
                  isActive ? "bg-background text-primary shadow-sm" : ""
                }`}
                aria-label={`Сортировать: ${header.label}`}
              >
                <SortIcon className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ProductDecisionCard({ item, onOpen }: { item: any; onOpen: () => void }) {
  const meta = statusMeta(item.status);
  const Icon = meta.icon;
  const trend = trendMeta(item);
  const coverage = coveragePercent(item);
  const recommended = recommendText(item);
  const unitProfit = num(item.net_profit_per_unit);
  const unitProfitTone = item.net_profit_per_unit == null ? "neutral" : unitProfit >= 0 ? "success" : "danger";
  const stockValue = num(item.stock_value ?? item.frozen_cash);
  const sales30 = num(item.sales_30d);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group relative grid w-full grid-cols-[68px_minmax(240px,1.25fr)_92px_100px_92px_118px_112px_100px_72px] items-center gap-3 bg-background px-3 py-2 text-left transition hover:bg-muted/25"
    >
      <span className={`absolute inset-y-0 left-0 w-0.5 ${meta.accent ?? "bg-primary"}`} />
      <ProductImage item={item} className="h-[68px] w-[54px]" />

      <div className="min-w-0">
        <div className="mb-1 flex min-w-0 items-center gap-1.5">
          <span className={`inline-flex h-5 max-w-[128px] items-center gap-1 rounded px-1.5 text-[10px] font-medium ${meta.tone}`}>
            <Icon className="h-3 w-3 shrink-0" />
            <span className="truncate">{meta.short}</span>
          </span>
          {item.financial_final === false && (
            <span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
              расчет
            </span>
          )}
        </div>
        <div className="line-clamp-2 text-[13px] font-semibold leading-snug text-foreground" title={item.title ?? item.name}>
          {item.title ?? item.name ?? item.vendor_code ?? "Товар"}
        </div>
        <div className="mt-1 flex min-w-0 gap-2 text-[11px] text-muted-foreground">
          <span className="shrink-0">nm {item.nm_id ?? "—"}</span>
          <span className="min-w-0 truncate">{item.vendor_code ?? item.barcode ?? "без артикула"}</span>
        </div>
      </div>

      <RowMetric value={formatNumber(num(item.available_stock))} sub={`${formatNumber(num(item.in_transit_qty))} в пути`} />
      <RowMetric value={formatNumber(sales30)} sub={`${formatDecimal(num(item.sales_velocity_daily), 1)} шт/день`} />
      <RowMetric value={trend.label} sub={trend.sub} tone={trend.tone} />
      <RowMetric value={formatMoney(stockValue)} sub={num(item.required_cash) > 0 ? `нужно ${formatMoney(num(item.required_cash))}` : "без закупки"} />
      <RowMetric value={recommended} sub={coverage.label} progress={coverage.value} />
      <RowMetric value={formatSignedMoney(item.net_profit_per_unit)} sub={profitabilityText(item)} tone={unitProfitTone} />

      <div className="flex justify-end">
        <span className="inline-flex h-7 items-center gap-1 rounded-md border bg-background px-2 text-[11px] font-medium text-muted-foreground transition group-hover:border-primary/40 group-hover:text-primary">
          Открыть
          <ArrowRight className="h-3.5 w-3.5" />
        </span>
      </div>
    </button>
  );
}

function RowMetric({ value, sub, tone, progress }: any) {
  const toneClass =
    tone === "danger"
      ? "text-rose-700"
      : tone === "success"
      ? "text-emerald-700"
      : tone === "warning"
      ? "text-amber-700"
      : "text-foreground";
  return (
    <div className="min-w-0">
      <div className={`truncate text-[13px] font-semibold leading-5 tabular-nums ${toneClass}`} title={String(value ?? "")}>
        {value}
      </div>
      {progress != null ? (
        <div className="mt-1">
          <Progress value={progress} className="h-1" />
          <div className="mt-1 truncate text-[10px] leading-3 text-muted-foreground" title={String(sub ?? "")}>
            {sub}
          </div>
        </div>
      ) : (
        <div className="truncate text-[10px] leading-3 text-muted-foreground" title={String(sub ?? "")}>
          {sub}
        </div>
      )}
    </div>
  );
}

function ProductDetailSheet({ item, open, onOpenChange }: { item: any | null; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [tab, setTab] = useState("overview");
  useEffect(() => {
    if (open) setTab("overview");
  }, [open, item?.nm_id]);

  if (!item) {
    return <Sheet open={open} onOpenChange={onOpenChange} />;
  }

  const meta = statusMeta(item.status);
  const Icon = meta.icon;
  const regions = arr(item.region_breakdown);
  const warehouses = arr(item.warehouse_breakdown);
  const sizes = arr(item.size_breakdown);
  const trend = trendMeta(item);
  const unitProfitTone = item.net_profit_per_unit == null ? "neutral" : num(item.net_profit_per_unit) >= 0 ? "success" : "danger";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full p-0 sm:max-w-3xl xl:max-w-4xl">
        <ScrollArea className="h-full">
          <div className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
            <div className="p-4 pr-10">
              <SheetHeader className="text-left">
                <div className="flex gap-3">
                  <ProductImage item={item} className="h-20 w-16 rounded-lg" />
                  <div className="min-w-0 flex-1">
                    <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                      <Badge variant="outline" className={`text-[10px] ${meta.tone}`}>
                        <Icon className="mr-1 h-3 w-3" />
                        {meta.label}
                      </Badge>
                      <Badge variant="outline" className="bg-background text-[10px]">
                        {item.variant_count || sizes.length || 1} размер
                      </Badge>
                      {item.financial_final === false && (
                        <Badge variant="outline" className="border-amber-300 bg-amber-50 text-[10px] text-amber-800">
                          расчетные данные
                        </Badge>
                      )}
                    </div>
                    <SheetTitle className="line-clamp-2 text-base leading-snug">
                      {item.title ?? item.vendor_code ?? "Товар"}
                    </SheetTitle>
                    <SheetDescription className="mt-1 text-xs">
                      nm {item.nm_id ?? "—"} · {item.vendor_code ?? "без артикула"} · {item.subject_name ?? item.brand ?? "без категории"}
                    </SheetDescription>
                  </div>
                </div>
              </SheetHeader>

              <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
                <CompactKpi label="Остаток" value={formatNumber(num(item.available_stock))} />
                <CompactKpi label="Продажи 30 дней" value={formatNumber(num(item.sales_30d))} />
                <CompactKpi label="Деньги в остатке" value={formatMoney(num(item.stock_value ?? item.frozen_cash))} />
                <CompactKpi label="Прибыль с 1 шт." value={formatSignedMoney(item.net_profit_per_unit)} tone={unitProfitTone} />
              </div>

              <Tabs value={tab} onValueChange={setTab} className="mt-3">
                <TabsList className="grid h-9 grid-cols-4 rounded-md bg-muted p-1">
                  <TabsTrigger value="overview" className="text-[11px]">Главное</TabsTrigger>
                  <TabsTrigger value="regions" className="text-[11px]">Регионы</TabsTrigger>
                  <TabsTrigger value="sizes" className="text-[11px]">Размеры</TabsTrigger>
                  <TabsTrigger value="calc" className="text-[11px]">Расчет</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
          </div>

          <div className="p-4 pr-10">
            {tab === "overview" && (
              <div className="space-y-3">
                <DecisionPanel item={item} />
                <div className="grid gap-2 md:grid-cols-2">
                  <InfoRow icon={Activity} label="Скорость продаж" value={`${formatDecimal(num(item.sales_velocity_daily), 2)} шт/день`} />
                  <InfoRow icon={trend.icon} label="Динамика продаж" value={`${trend.label} · ${trend.sub}`} tone={trend.tone} />
                  <InfoRow icon={Clock} label="Покрытие остатка" value={item.days_of_stock != null ? `${Math.round(item.days_of_stock)} дней` : "не рассчитано"} />
                  <InfoRow icon={Wallet} label="Маржа / ROI" value={`${formatPercent(num(item.margin_percent))} / ${formatPercent(num(item.roi_percent))}`} tone={num(item.expected_profit) < 0 ? "danger" : "success"} />
                </div>
                <Separator />
                <div className="rounded-lg border bg-muted/20 p-3">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Причина решения</div>
                  <div className="text-sm leading-relaxed">{item.reason || "—"}</div>
                  <div className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Следующий шаг</div>
                  <div className="mt-1 text-sm leading-relaxed">{item.next_step || recommendText(item)}</div>
                </div>
              </div>
            )}

            {tab === "regions" && (
              <div className="space-y-3">
                {regions.length > 0 ? (
                  regions.map((region: any, index: number) => (
                    <div key={`${region.region_name}-${index}`} className="rounded-lg border bg-background p-3 shadow-sm">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 text-sm font-semibold">
                            <MapPin className="h-4 w-4 text-cyan-600" />
                            <span className="truncate">{region.region_name ?? "Регион"}</span>
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {arr(region.warehouses).length || 0} складов
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-base font-semibold tabular-nums">{formatNumber(num(region.quantity))}</div>
                          <div className="text-xs text-muted-foreground">{formatNumber(num(region.in_transit_qty))} в пути</div>
                        </div>
                      </div>
                      <div className="mt-3 grid gap-1.5">
                        {arr(region.warehouses).slice(0, 8).map((wh: any, whIndex: number) => (
                          <div key={`${wh.warehouse_name}-${whIndex}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 rounded-lg bg-muted/35 px-3 py-2 text-xs">
                            <span className="min-w-0 truncate">{wh.warehouse_name ?? wh.office_name ?? "Склад"}</span>
                            <span className="font-semibold tabular-nums">{formatNumber(num(wh.quantity))} шт.</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                ) : (
                  <EmptyDetail icon={MapPin} text="Разбивка по регионам и складам пока не пришла." />
                )}

                {warehouses.length > regions.length && (
                  <div className="rounded-lg border bg-background p-3 shadow-sm">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Складские строки</div>
                    <div className="grid gap-1.5">
                      {warehouses.slice(0, 12).map((wh: any, index: number) => (
                        <div key={index} className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2 rounded-lg bg-muted/35 px-3 py-2 text-xs">
                          <span className="truncate">{wh.warehouse_name ?? wh.region_name ?? "Склад"}</span>
                          <span>{wh.tech_size ?? wh.barcode ?? "—"}</span>
                          <span className="font-semibold tabular-nums">{formatNumber(num(wh.quantity))}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {tab === "sizes" && (
              <div className="space-y-2">
                {sizes.length > 0 ? (
                  sizes.map((size: any, index: number) => (
                    <div key={`${size.sku_id}-${index}`} className="rounded-lg border bg-background p-3 shadow-sm">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 text-sm font-semibold">
                            <Ruler className="h-4 w-4 text-violet-600" />
                            <span>{size.tech_size ?? size.size ?? size.sku_id ?? `#${index + 1}`}</span>
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            barcode {size.barcode ?? "—"} · sku {size.sku_id ?? "—"}
                          </div>
                        </div>
                        <Badge variant="outline" className={statusMeta(size.status).tone}>
                          {statusMeta(size.status).short}
                        </Badge>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
                        <CompactKpi label="Остаток" value={formatNumber(num(size.available_stock))} />
                        <CompactKpi label="Продажи 30 дней" value={formatNumber(num(size.sales_30d))} />
                        <CompactKpi label="Закупить" value={formatNumber(num(size.recommended_qty))} />
                        <CompactKpi
                          label="Прибыль с 1 шт."
                          value={formatSignedMoney(size.net_profit_per_unit)}
                          tone={size.net_profit_per_unit == null ? "neutral" : num(size.net_profit_per_unit) >= 0 ? "success" : "danger"}
                        />
                      </div>
                    </div>
                  ))
                ) : (
                  <EmptyDetail icon={Ruler} text="Разбивки по размерам пока нет." />
                )}
              </div>
            )}

            {tab === "calc" && (
              <div className="space-y-3">
                <FormulaBlock item={item} />
                <div className="grid gap-2 md:grid-cols-2">
                  <InfoRow icon={Package} label="Нужный запас" value={`${formatDecimal(requiredStock(item), 1)} шт.`} />
                  <InfoRow icon={Boxes} label="Есть + в пути" value={`${formatDecimal(num(item.available_stock) + num(item.in_transit_qty), 1)} шт.`} />
                  <InfoRow icon={ShoppingCart} label="Рекомендация" value={recommendText(item)} />
                  <InfoRow icon={Wallet} label="Бюджет закупки" value={formatMoney(num(item.required_cash))} />
                  <InfoRow icon={BarChart3} label="Ожидаемая прибыль" value={formatSignedMoney(item.expected_profit)} tone={num(item.expected_profit) < 0 ? "danger" : "success"} />
                  <InfoRow icon={Info} label="Уровень данных" value={item.financial_final === false ? "расчетные" : "финальные"} />
                </div>
                {arr(item.missing_data).length > 0 && (
                  <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-amber-950">
                    <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                      <AlertTriangle className="h-4 w-4" />
                      Не хватает данных
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {arr(item.missing_data).map((value: any) => (
                        <Badge key={String(value)} variant="outline" className="border-amber-300 bg-background/70">
                          {missingLabel(value)}
                        </Badge>
                      ))}
                    </div>
                    <Button asChild size="sm" className="mt-3">
                      <Link to="/data-fix" search={{ financial_final_blocker: true, only_open: true, severity: "error,warning" }}>
                        <Wrench className="mr-1.5 h-3.5 w-3.5" />
                        Исправить данные
                      </Link>
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}

function FilterPopover({
  activeCount,
  profitFilter,
  setProfitFilter,
  dataFilter,
  setDataFilter,
  stockFilter,
  setStockFilter,
  groupBy,
  setGroupBy,
  onReset,
}: any) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={`h-8 gap-2 rounded-full border-dashed px-3 text-xs shadow-sm ${
            activeCount ? "border-primary/50 bg-primary/5 text-primary" : "bg-background"
          }`}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
          Фильтры
          {activeCount > 0 && (
            <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
              {activeCount}
            </span>
          )}
          <ChevronDown className="h-3.5 w-3.5 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(92vw,560px)] rounded-xl p-0 shadow-xl">
        <div className="border-b px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Фильтры закупки</div>
              <div className="mt-0.5 text-xs text-muted-foreground">Выберите только нужные срезы, список обновится сразу.</div>
            </div>
            {activeCount > 0 && (
              <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={onReset}>
                Сбросить
              </Button>
            )}
          </div>
        </div>
        <div className="grid gap-4 p-4 md:grid-cols-2">
          <FilterOptionGroup
            title="Прибыль"
            value={profitFilter}
            onChange={setProfitFilter}
            options={PROFIT_FILTERS}
          />
          <FilterOptionGroup
            title="Данные"
            value={dataFilter}
            onChange={setDataFilter}
            options={DATA_FILTERS}
          />
          <FilterOptionGroup
            title="Остатки"
            value={stockFilter}
            onChange={setStockFilter}
            options={STOCK_FILTERS}
          />
          <FilterOptionGroup
            title="Группировка"
            value={groupBy}
            onChange={setGroupBy}
            options={GROUP_OPTIONS}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}

function FilterOptionGroup({ title, value, onChange, options }: any) {
  return (
    <div className="space-y-2">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option: any) => {
          const active = value === option.value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange(option.value)}
              className={`inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition ${
                active
                  ? "border-primary/50 bg-primary text-primary-foreground shadow-sm"
                  : "border-border bg-background text-muted-foreground hover:border-primary/40 hover:text-foreground"
              }`}
            >
              {active && <Check className="h-3.5 w-3.5" />}
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ActiveFilterChip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span className="inline-flex h-8 items-center gap-1.5 rounded-full border bg-background px-2.5 text-xs text-muted-foreground shadow-sm">
      <span className="max-w-[180px] truncate">{label}</span>
      <button
        type="button"
        onClick={onClear}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full transition hover:bg-muted hover:text-foreground"
        aria-label={`Убрать фильтр ${label}`}
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

function SummaryGrid({ stats }: { stats: any }) {
  return (
    <section className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
      <SummaryTile icon={Package} label="Товары" value={formatNumber(stats.total)} sub={`${formatNumber(stats.pageCount)} показано`} tone="neutral" />
      <SummaryTile icon={ShoppingCart} label="Нужно закупить" value={formatNumber(stats.reorder)} sub={formatMoney(stats.requiredCash)} tone="success" />
      <SummaryTile icon={TrendingDown} label="Излишки" value={formatNumber(stats.liquidate)} sub={formatMoney(stats.frozenCash)} tone="warning" />
      <SummaryTile icon={Ban} label="Не покупать" value={formatNumber(stats.doNotBuy)} sub="юнит-экономика ниже нормы" tone="danger" />
      <SummaryTile icon={AlertTriangle} label="Нужны данные" value={formatNumber(stats.waitData)} sub="финансы / себестоимость / остатки" tone="info" />
    </section>
  );
}

function SummaryTile({ icon: Icon, label, value, sub, tone }: any) {
  const tones: any = {
    success: "border-emerald-200 bg-emerald-50/40 text-emerald-900",
    warning: "border-amber-200 bg-amber-50/40 text-amber-950",
    danger: "border-rose-200 bg-rose-50/40 text-rose-900",
    info: "border-cyan-200 bg-cyan-50/40 text-cyan-900",
    neutral: "border-border bg-background text-foreground",
  };
  return (
    <Card className={`rounded-lg shadow-sm ${tones[tone] ?? tones.neutral}`}>
      <CardContent className="flex items-center gap-2.5 p-2.5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-background/80">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="text-[11px] font-medium text-muted-foreground">{label}</div>
          <div className="truncate text-base font-semibold leading-5 tabular-nums">{value}</div>
          <div className="truncate text-[11px] text-muted-foreground">{sub}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function MetricCell({ icon: Icon, label, value, sub, tone, progress }: any) {
  const toneClass = tone === "danger" ? "text-rose-700" : tone === "success" ? "text-emerald-700" : tone === "warning" ? "text-amber-700" : "";
  return (
    <div className="min-w-0 rounded-md bg-background/70 px-2 py-1.5 ring-1 ring-border/60">
      <div className="flex min-w-0 items-center gap-1.5 text-[11px] text-muted-foreground">
        <Icon className={`h-3.5 w-3.5 ${toneClass}`} />
        <span className="min-w-0 truncate">{label}</span>
      </div>
      <div className={`mt-0.5 min-h-5 whitespace-normal break-words text-sm font-semibold leading-tight tabular-nums ${toneClass}`}>
        {value}
      </div>
      {progress != null ? (
        <div className="mt-1">
          <Progress value={progress} className="h-1.5" />
          <div className="mt-1 min-w-0 truncate text-[11px] text-muted-foreground">{sub}</div>
        </div>
      ) : (
        <div className="mt-0.5 min-w-0 truncate text-[11px] text-muted-foreground">{sub}</div>
      )}
    </div>
  );
}

function DecisionPanel({ item }: { item: any }) {
  const meta = statusMeta(item.status);
  const Icon = meta.icon;
  return (
    <div className={`rounded-lg border p-2.5 ${meta.tone}`}>
      <div className="flex items-start gap-2.5">
        <Icon className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <div className="text-sm font-semibold leading-5">{recommendText(item)}</div>
          <div className="mt-1 text-xs opacity-80">{item.next_step || meta.label}</div>
        </div>
      </div>
    </div>
  );
}

function FormulaBlock({ item }: { item: any }) {
  const need = requiredStock(item);
  const have = num(item.available_stock) + num(item.in_transit_qty);
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <div className="mb-2 text-sm font-semibold">Формула закупки</div>
      <div className="grid gap-2 text-sm">
        <FormulaLine label="Средние продажи в день" value={`${formatDecimal(num(item.sales_velocity_daily), 2)} шт.`} />
        <FormulaLine label="Срок поставки + страховой запас" value={`${item.lead_time_days ?? 14} + ${item.safety_days ?? 7} дней`} />
        <FormulaLine label="Нужный запас" value={`${formatDecimal(need, 1)} шт.`} />
        <FormulaLine label="Есть + в пути" value={`${formatDecimal(have, 1)} шт.`} />
        <FormulaLine label="Рекомендованная закупка" value={formatNumber(num(item.recommended_qty))} strong />
      </div>
    </div>
  );
}

function FormulaLine({ label, value, strong }: any) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md bg-background px-2 py-1.5">
      <span className="text-muted-foreground">{label}</span>
      <span className={`tabular-nums ${strong ? "font-semibold" : ""}`}>{value}</span>
    </div>
  );
}

function InfoRow({ icon: Icon, label, value, tone }: any) {
  const toneClass = tone === "danger" ? "text-rose-700" : tone === "success" ? "text-emerald-700" : tone === "warning" ? "text-amber-700" : "";
  return (
    <div className="flex items-center gap-2.5 rounded-lg border p-2.5">
      <Icon className={`h-4 w-4 shrink-0 ${toneClass || "text-muted-foreground"}`} />
      <div className="min-w-0">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className={`truncate text-sm font-semibold ${toneClass}`}>{value}</div>
      </div>
    </div>
  );
}

function CompactKpi({ label, value, tone }: any) {
  const toneClass = tone === "danger" ? "text-rose-700" : tone === "success" ? "text-emerald-700" : "";
  return (
    <div className="rounded-lg border bg-background p-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={`mt-0.5 truncate text-[13px] font-semibold tabular-nums ${toneClass}`}>{value}</div>
    </div>
  );
}

function ProductImage({ item, className }: { item: any; className?: string }) {
  const src = imageUrl(item);
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <div className={`flex shrink-0 items-center justify-center rounded-md border bg-muted/30 text-muted-foreground ${className}`}>
        <ImageOff className="h-6 w-6" />
      </div>
    );
  }
  return (
    <div className={`shrink-0 overflow-hidden rounded-md border bg-muted ${className}`}>
      <img
        src={src}
        alt=""
        className="h-full w-full object-cover"
        loading="lazy"
        onError={() => setFailed(true)}
      />
    </div>
  );
}

function EmptyDetail({ icon: Icon, text }: any) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-muted/20 p-6 text-center">
      <Icon className="h-7 w-7 text-muted-foreground" />
      <div className="text-sm text-muted-foreground">{text}</div>
    </div>
  );
}

function PaginationBar({ limit, offset, shown, pageItems, total, isFetching, onLimit, onPrev, onNext }: any) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background p-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>На странице</span>
        <select
          value={limit}
          onChange={(event) => onLimit(Number(event.target.value))}
          className="h-8 rounded-md border border-input bg-background px-2 text-xs"
        >
          {[25, 50, 100, 200].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <span>{formatNumber(shown)} / {formatNumber(total)}</span>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" disabled={offset === 0 || isFetching} onClick={onPrev}>
          Назад
        </Button>
        <span className="text-xs tabular-nums text-muted-foreground">
          {offset + 1}-{offset + shown}
        </span>
        <Button size="sm" variant="outline" disabled={isFetching || pageItems < limit} onClick={onNext}>
          Вперед
        </Button>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-3">
      <div className="grid gap-2 md:grid-cols-5">
        {[1, 2, 3, 4, 5].map((item) => (
          <Skeleton key={item} className="h-20 rounded-lg" />
        ))}
      </div>
      {[1, 2, 3, 4].map((item) => (
        <Skeleton key={item} className="h-28 rounded-lg" />
      ))}
    </div>
  );
}

function extractItems(data: any): any[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  return data.items ?? data.rows ?? data.articles ?? data.plan ?? [];
}

function buildStats(items: any[], summary: any) {
  const local = { reorder: 0, liquidate: 0, doNotBuy: 0, waitData: 0, watch: 0, frozenCash: 0, requiredCash: 0 };
  for (const item of items) {
    const status = statusCode(item);
    if (status === "REORDER") {
      local.reorder += 1;
      local.requiredCash += num(item.required_cash);
    } else if (status === "LIQUIDATE") {
      local.liquidate += 1;
    } else if (status === "DO_NOT_BUY" || status === "DO_NOT_REORDER") {
      local.doNotBuy += 1;
    } else if (status === "WAIT_DATA") {
      local.waitData += 1;
    } else {
      local.watch += 1;
    }
    local.frozenCash += num(item.stock_value ?? item.frozen_cash);
  }
  return {
    pageCount: items.length,
    total: Number(summary.total_positions ?? summary.total_items ?? summary.total_count ?? items.length),
    reorder: Number(summary.reorder_count ?? local.reorder),
    liquidate: Number(summary.liquidate_count ?? local.liquidate),
    doNotBuy: Number(summary.do_not_buy_count ?? local.doNotBuy),
    waitData: Number(summary.wait_data_count ?? local.waitData),
    watch: Number(summary.watch_count ?? local.watch),
    requiredCash: num(summary.total_required_cash ?? summary.required_cash_total) || local.requiredCash,
    frozenCash: num(summary.total_stock_value ?? summary.frozen_cash_total) || local.frozenCash,
  };
}

function filterItems(items: any[], filter: string, search: string) {
  const query = search.trim().toLowerCase();
  let list = items;
  if (filter === "actionable") {
    list = items.filter((item) => ["REORDER", "LIQUIDATE", "DO_NOT_BUY", "DO_NOT_REORDER", "PROTECT_STOCK"].includes(statusCode(item)));
  } else if (filter !== "all") {
    list = items.filter((item) => {
      const status = statusCode(item);
      if (filter === "DO_NOT_BUY") return status === "DO_NOT_BUY" || status === "DO_NOT_REORDER";
      return status === filter;
    });
  }
  if (query) {
    list = list.filter((item) =>
      [item.nm_id, item.vendor_code, item.barcode, item.title, item.name, item.brand, item.subject_name]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query)),
    );
  }
  const rank: any = { REORDER: 0, LIQUIDATE: 1, DO_NOT_BUY: 2, DO_NOT_REORDER: 2, PROTECT_STOCK: 3, WAIT_DATA: 4, WATCH: 5 };
  return [...list].sort((a, b) => (rank[statusCode(a)] ?? 9) - (rank[statusCode(b)] ?? 9));
}

function filterCount(key: string, stats: any) {
  if (key === "actionable") return stats.reorder + stats.liquidate + stats.doNotBuy;
  if (key === "REORDER") return stats.reorder;
  if (key === "LIQUIDATE") return stats.liquidate;
  if (key === "DO_NOT_BUY") return stats.doNotBuy;
  if (key === "WAIT_DATA") return stats.waitData;
  return stats.total;
}

function statusCode(item: any) {
  return String(item?.status ?? item?.decision ?? "WATCH").toUpperCase();
}

function statusMeta(status: string | undefined) {
  return STATUS_META[statusCode({ status })] ?? STATUS_META.WATCH;
}

function rowKey(item: any) {
  return `${item.nm_id ?? "nm"}-${item.sku_id ?? item.vendor_code ?? item.id ?? "row"}`;
}

function num(value: any): number {
  if (value === null || value === undefined || value === "") return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function arr(value: any): any[] {
  return Array.isArray(value) ? value : [];
}

function optionLabel(options: any[], value: any) {
  return options.find((option) => option.value === value)?.label ?? String(value ?? "");
}

function sortLabel(sortKey: string) {
  const [field, dir] = String(sortKey || "").split(":");
  const labels: any = {
    available_stock: "Остаток",
    sales_30d: "Продажи",
    trend: "Динамика",
    stock_value: "В остатке",
    recommended_qty: "Закупка",
    unit_profit: "1 шт.",
  };
  const arrow = dir === "asc" ? "↑" : "↓";
  return `${labels[field] ?? field} ${arrow}`;
}

function imageUrl(item: any): string | null {
  const direct = item?.photo_url ?? item?.image_url ?? item?.photo ?? item?.image;
  if (typeof direct === "string" && direct.startsWith("http")) return direct;
  const photos = item?.photos;
  if (Array.isArray(photos)) {
    for (const photo of photos) {
      const url = imageUrl(photo);
      if (url) return url;
    }
  }
  if (photos && typeof photos === "object") return imageUrl(photos);
  for (const key of ["big", "hq", "canonical_url", "url", "full", "src", "c516x688", "square", "c246x328", "tm"]) {
    const value = item?.[key];
    if (typeof value === "string" && value.startsWith("http")) return value;
  }
  return null;
}

function trendMeta(item: any) {
  const direction = String(item.sales_trend_direction ?? "").toLowerCase();
  const units = num(item.sales_trend_units);
  const percent = item.sales_trend_percent == null ? null : Number(item.sales_trend_percent);
  if (direction === "up" || units > 0) {
    return {
      icon: TrendingUp,
      label: percent == null ? `+${formatNumber(units)}` : `+${formatPercent(percent)}`,
      sub: `+${formatNumber(units)} шт.`,
      tone: "success",
    };
  }
  if (direction === "down" || units < 0) {
    return {
      icon: TrendingDown,
      label: percent == null ? formatNumber(units) : formatPercent(percent),
      sub: `${formatNumber(units)} шт.`,
      tone: "danger",
    };
  }
  return { icon: Minus, label: "без изменений", sub: "динамика ровная", tone: "neutral" };
}

function coveragePercent(item: any) {
  const days = item.days_of_stock == null ? null : num(item.days_of_stock);
  const target = num(item.lead_time_days) + num(item.safety_days);
  if (days == null || target <= 0) return { value: 0, label: "дней нет" };
  return { value: Math.max(0, Math.min(100, (days / target) * 100)), label: `${Math.round(days)} / ${Math.round(target)} дней` };
}

function recommendText(item: any) {
  const status = statusCode(item);
  if (status === "REORDER") return `Купить ${formatNumber(num(item.recommended_qty))} шт.`;
  if (status === "LIQUIDATE") return "Новую закупку не делать";
  if (status === "DO_NOT_BUY" || status === "DO_NOT_REORDER") return "Не покупать";
  if (status === "WAIT_DATA") return "Сначала исправить данные";
  if (status === "PROTECT_STOCK") return "Дождаться товара в пути";
  return "Запаса достаточно";
}

function profitabilityText(item: any) {
  const profit = item.net_profit_per_unit == null ? null : num(item.net_profit_per_unit);
  if (profit == null) return "прибыль не рассчитана";
  return profit >= 0 ? "в плюсе" : "в минусе";
}

function requiredStock(item: any) {
  return num(item.sales_velocity_daily) * (num(item.lead_time_days) + num(item.safety_days));
}

function formatDecimal(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString("ru-RU", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

function formatSignedMoney(value: any) {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  const formatted = formatMoney(Math.abs(parsed));
  if (parsed > 0) return `+${formatted}`;
  if (parsed < 0) return `-${formatted}`;
  return formatted;
}

function missingLabel(value: any) {
  const key = String(value ?? "").toLowerCase();
  const labels: any = {
    finance: "финальные финансы",
    cost: "себестоимость",
    stock: "остатки",
    velocity: "скорость продаж",
    sales: "история продаж",
  };
  return labels[key] ?? String(value);
}
