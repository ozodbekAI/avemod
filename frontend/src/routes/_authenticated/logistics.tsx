import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type Column,
  type ColumnDef,
  type SortingState,
  type Table as ReactTableInstance,
} from "@tanstack/react-table";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUpRight,
  ArrowUpDown,
  Boxes,
  Calculator,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  ClipboardList,
  Clock,
  Database,
  Download,
  Factory,
  FileSpreadsheet,
  Gauge,
  Layers3,
  ListChecks,
  MapPin,
  PackageCheck,
  PackagePlus,
  PackageSearch,
  RefreshCw,
  Route as RouteIcon,
  Search,
  Settings2,
  ShieldCheck,
  Target,
  TrendingDown,
  Truck,
  Warehouse,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { EndpointError } from "@/components/EndpointError";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Slider } from "@/components/ui/slider";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useAccounts } from "@/lib/account-context";
import { api } from "@/lib/api";
import { useDateRange } from "@/lib/date-range-context";
import { API_ENDPOINTS } from "@/lib/endpoints";
import {
  formatDate,
  formatDateTime,
  formatMoney,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_authenticated/logistics")({
  component: LogisticsPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

type LogisticsOverview = {
  account_id: number;
  period: { date_from: string; date_to: string };
  kpis: LogisticsKpis;
  warehouses: WarehouseRow[];
  supplies: SupplyRow[];
  tasks?: LogisticsTaskRow[];
  products?: ProductRow[];
  regional_shipments?: RegionalShipmentRow[];
  warehouse_controls?: WarehouseControlRow[];
  paid_storage_details?: PaidStorageDetailRow[];
  acceptance_details?: AcceptanceDetailRow[];
  transit_tariffs?: TransitTariffRow[];
  seller_warehouses?: SellerWarehouseRow[];
  data_sources: DataSourceRow[];
  api_capabilities: CapabilityRow[];
  recommendations: RecommendationRow[];
  generated_at: string;
};

type LogisticsKpis = {
  orders_qty: number;
  sales_qty: number;
  revenue: number;
  for_pay: number;
  logistics_cost: number;
  storage_cost: number;
  acceptance_cost: number;
  return_logistics_cost: number;
  missed_orders_qty: number;
  missed_revenue: number;
  cancelled_orders_qty: number;
  cancelled_revenue: number;
  stock_units: number;
  in_way_to_client: number;
  in_way_from_client: number;
  active_warehouses: number;
  risky_warehouses: number;
  available_acceptance_slots: number;
  avg_logistics_per_order?: number | null;
  logistics_share_percent?: number | null;
  buyout_percent?: number | null;
  margin_percent?: number | null;
  paid_storage_detail_cost?: number;
  paid_storage_detail_rows?: number;
  acceptance_detail_cost?: number;
  acceptance_detail_rows?: number;
  transit_route_count?: number;
  seller_warehouse_count?: number;
  seller_stock_units?: number;
};

type WarehouseRow = {
  warehouse_id?: number | null;
  warehouse_name: string;
  region_name?: string | null;
  stock_units: number;
  in_way_to_client: number;
  in_way_from_client: number;
  orders_qty: number;
  sales_qty: number;
  revenue: number;
  for_pay: number;
  revenue_source?: string | null;
  finance_rows?: number | null;
  logistics_cost: number;
  storage_cost: number;
  acceptance_cost: number;
  return_logistics_cost: number;
  cancelled_orders_qty: number;
  cancelled_revenue: number;
  missed_orders_qty: number;
  missed_revenue: number;
  buyout_percent?: number | null;
  logistics_share_percent?: number | null;
  margin_percent?: number | null;
  turnover_days?: number | null;
  acceptance_coefficient?: string | null;
  acceptance_status: "available" | "expensive" | "closed" | "unknown" | string;
  allow_unload?: boolean | null;
  acceptance_next_available_at?: string | null;
  acceptance_box_type_id?: number | null;
  box_type_ids: number[];
  delivery_base?: number | null;
  delivery_liter?: number | null;
  storage_base?: number | null;
  region_sales_qty: number;
  region_sales_amount: number;
  region_sales_share_percent?: number | null;
  supply_count: number;
  open_supply_count: number;
  risk_level: "ok" | "watch" | "warning" | "danger" | string;
  recommendation?: string | null;
};

type SupplyRow = {
  supply_id: number;
  preorder_id?: number | null;
  warehouse_name?: string | null;
  actual_warehouse_name?: string | null;
  status_id?: number | null;
  status_label: string;
  supply_date?: string | null;
  fact_date?: string | null;
  planned_qty: number;
  accepted_qty: number;
  gap_qty: number;
  box_type_id?: number | null;
  last_enriched_at?: string | null;
};

type DataSourceRow = {
  key: string;
  label: string;
  status: string;
  rows: number;
  latest_at?: string | null;
  note?: string | null;
};

type CapabilityRow = {
  key: string;
  label: string;
  endpoint: string;
  token_category: string;
  status: string;
  note?: string | null;
};

type RecommendationRow = {
  severity: "ok" | "watch" | "warning" | "danger" | string;
  title: string;
  detail: string;
  action: string;
  source?: string | null;
};

type LogisticsTaskRow = {
  id: string;
  task_type: string;
  severity: "ok" | "watch" | "warning" | "danger" | string;
  title: string;
  warehouse_name?: string | null;
  region_name?: string | null;
  detail: string;
  action: string;
  forecast_days?: number | null;
  stockout_in_days?: number | null;
  recommended_supply_qty: number;
  potential_orders_qty: number;
  potential_revenue: number;
  expected_net_effect: number;
  logistics_share_percent?: number | null;
  buyout_percent?: number | null;
  confidence: string;
  tags: string[];
};

type ProductRow = {
  id: string;
  nm_id?: number | null;
  vendor_code?: string | null;
  barcode?: string | null;
  title?: string | null;
  brand?: string | null;
  subject_name?: string | null;
  warehouse_name: string;
  region_name?: string | null;
  stock_units: number;
  in_way_to_client: number;
  in_way_from_client: number;
  orders_qty: number;
  sales_qty: number;
  cancelled_orders_qty: number;
  cancelled_revenue: number;
  revenue: number;
  for_pay: number;
  revenue_source?: string | null;
  finance_rows?: number | null;
  logistics_cost: number;
  storage_cost: number;
  acceptance_cost: number;
  return_logistics_cost: number;
  buyout_percent?: number | null;
  logistics_share_percent?: number | null;
  margin_percent?: number | null;
  avg_daily_sales: number;
  turnover_days?: number | null;
  recommended_supply_14: number;
  recommended_supply_30: number;
  potential_orders_qty: number;
  potential_revenue: number;
  expected_net_effect: number;
  risk_level: "ok" | "watch" | "warning" | "danger" | string;
  reason?: string | null;
  tags: string[];
};

type RegionalShipmentRow = {
  id: string;
  warehouse_name: string;
  region_name?: string | null;
  recommended_supply_qty: number;
  potential_orders_qty: number;
  potential_revenue: number;
  region_sales_qty: number;
  region_sales_amount: number;
  region_sales_share_percent?: number | null;
  expected_logistics_cost: number;
  expected_net_effect: number;
  current_stock_units: number;
  turnover_days?: number | null;
  acceptance_status: string;
  acceptance_coefficient?: string | null;
  priority: string;
  reason: string;
  tags: string[];
};

type WarehouseControlRow = {
  warehouse_name: string;
  region_name?: string | null;
  mode: string;
  recommended_mode: string;
  task_count: number;
  potential_revenue: number;
  stock_units: number;
  turnover_days?: number | null;
  acceptance_status: string;
  logistics_share_percent?: number | null;
  reason?: string | null;
};

type PaidStorageDetailRow = {
  id: number;
  report_date?: string | null;
  warehouse_name?: string | null;
  nm_id?: number | null;
  vendor_code?: string | null;
  barcode?: string | null;
  title?: string | null;
  brand?: string | null;
  subject_name?: string | null;
  quantity: number;
  amount: number;
  amount_per_unit?: number | null;
  share_percent?: number | null;
  task_id?: string | null;
  source_row_key?: string | null;
};

type AcceptanceDetailRow = {
  id: number;
  operation_date?: string | null;
  warehouse_name?: string | null;
  operation_name?: string | null;
  nm_id?: number | null;
  vendor_code?: string | null;
  barcode?: string | null;
  title?: string | null;
  brand?: string | null;
  subject_name?: string | null;
  quantity: number;
  amount: number;
  amount_per_unit?: number | null;
  share_percent?: number | null;
  task_id?: string | null;
  source_row_key?: string | null;
};

type TransitTariffRow = {
  id: number;
  collected_at: string;
  route_label?: string | null;
  source_warehouse_id?: number | null;
  source_warehouse_name?: string | null;
  transit_warehouse_id?: number | null;
  transit_warehouse_name?: string | null;
  destination_warehouse_id?: number | null;
  destination_warehouse_name?: string | null;
  box_type_id?: number | null;
  coefficient?: string | null;
  delivery_base?: number | null;
  delivery_liter?: number | null;
  amount?: number | null;
  currency?: string | null;
  transit_time_days?: number | null;
  score?: number | null;
};

type SellerWarehouseRow = {
  id: number;
  warehouse_id: number;
  name?: string | null;
  office_id?: number | null;
  delivery_type?: string | null;
  delivery_type_label?: string | null;
  cargo_type?: string | null;
  address?: string | null;
  is_active?: boolean | null;
  stock_rows: number;
  stock_units: number;
  latest_stock_at?: string | null;
};

type WarehouseCalculated = {
  totalLogistics: number;
  costPerOrder: number | null;
  costPerSale: number | null;
  avgDailySales: number;
  avgSaleValue: number | null;
  targetStock: number;
  replenishmentQty: number;
  stockCoveragePercent: number;
  marginAfterLogistics: number;
  priority: string;
};

type ShipmentBuilderMode = "warehouse" | "region";

type ShipmentLine = ProductRow & {
  selected: boolean;
  targetStock: number;
  shipmentQty: number;
  shipmentRevenue: number;
  shipmentNet: number;
};

type LogisticsExportDataset =
  | "tasks"
  | "regional"
  | "controls"
  | "warehouses"
  | "products"
  | "shipment"
  | "paid_storage"
  | "acceptance"
  | "transit"
  | "seller_warehouses";

const FAST_REPLENISHMENT_DAYS = 14;
const PRODUCTION_PLANNING_DAYS = 30;

function isLogisticsOverview(value: unknown): value is LogisticsOverview {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<LogisticsOverview>;
  return Boolean(
    candidate.period?.date_from &&
    candidate.period?.date_to &&
    candidate.kpis &&
    Array.isArray(candidate.warehouses) &&
    Array.isArray(candidate.supplies) &&
    Array.isArray(candidate.data_sources) &&
    Array.isArray(candidate.api_capabilities) &&
    Array.isArray(candidate.recommendations),
  );
}

function LogisticsPage() {
  const { activeId } = useAccounts();
  const range = useDateRange();
  const [search, setSearch] = useState("");
  const [selectedWarehouseName, setSelectedWarehouseName] = useState<
    string | null
  >(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [disabledWarehouses, setDisabledWarehouses] = useState<Set<string>>(
    () => new Set(),
  );
  const [exportingDataset, setExportingDataset] =
    useState<LogisticsExportDataset | null>(null);
  const debouncedSearch = useDebouncedValue(search, 250);

  const query = useQuery({
    queryKey: [
      "logistics-overview",
      activeId,
      range.from,
      range.to,
      debouncedSearch,
    ],
    enabled: !!activeId,
    queryFn: () =>
      api<LogisticsOverview>(API_ENDPOINTS.portal.logisticsOverview, {
        query: {
          account_id: activeId,
          date_from: range.from,
          date_to: range.to,
          search: debouncedSearch || undefined,
          warehouse_limit: 80,
          supply_limit: 30,
          product_limit: 160,
        },
      }),
    retry: false,
    staleTime: 60_000,
  });

  const rawData = query.data;
  const data = isLogisticsOverview(rawData) ? rawData : null;
  const hasUnexpectedPayload = Boolean(rawData && !data);
  const warehouses = useMemo(() => data?.warehouses ?? [], [data?.warehouses]);
  const rawTasks = useMemo(() => data?.tasks ?? [], [data?.tasks]);
  const rawProducts = useMemo(() => data?.products ?? [], [data?.products]);
  const rawRegionalShipments = useMemo(
    () => data?.regional_shipments ?? [],
    [data?.regional_shipments],
  );
  const periodDays = useMemo(
    () => getInclusiveDays(data?.period?.date_from, data?.period?.date_to),
    [data?.period?.date_from, data?.period?.date_to],
  );

  const visibleTasks = useMemo(
    () =>
      rawTasks.filter(
        (task) =>
          !task.warehouse_name || !disabledWarehouses.has(task.warehouse_name),
      ),
    [disabledWarehouses, rawTasks],
  );
  const products = useMemo(
    () =>
      rawProducts.filter((row) => !disabledWarehouses.has(row.warehouse_name)),
    [disabledWarehouses, rawProducts],
  );
  const regionalShipments = useMemo(
    () =>
      rawRegionalShipments.filter(
        (row) => !disabledWarehouses.has(row.warehouse_name),
      ),
    [disabledWarehouses, rawRegionalShipments],
  );

  const selectedWarehouse = useMemo(
    () =>
      warehouses.find((row) => row.warehouse_name === selectedWarehouseName) ??
      warehouses[0] ??
      null,
    [selectedWarehouseName, warehouses],
  );
  const selectedTask = useMemo(
    () =>
      visibleTasks.find((task) => task.id === selectedTaskId) ??
      visibleTasks[0] ??
      null,
    [selectedTaskId, visibleTasks],
  );

  useEffect(() => {
    if (!activeId || typeof window === "undefined") {
      setDisabledWarehouses(new Set());
      return;
    }
    try {
      const raw = localStorage.getItem(disabledWarehouseKey(activeId));
      const parsed = raw ? (JSON.parse(raw) as string[]) : [];
      setDisabledWarehouses(new Set(parsed));
    } catch {
      setDisabledWarehouses(new Set());
    }
  }, [activeId]);

  const toggleWarehouseTasks = (warehouseName: string) => {
    if (!activeId || typeof window === "undefined") return;
    setDisabledWarehouses((prev) => {
      const next = new Set(prev);
      if (next.has(warehouseName)) next.delete(warehouseName);
      else next.add(warehouseName);
      localStorage.setItem(
        disabledWarehouseKey(activeId),
        JSON.stringify(Array.from(next)),
      );
      return next;
    });
  };

  const exportCsv = async (dataset: LogisticsExportDataset) => {
    if (!activeId) return;
    setExportingDataset(dataset);
    try {
      const response = await api<Response>(
        API_ENDPOINTS.portal.logisticsExportCsv,
        {
          raw: true,
          query: {
            account_id: activeId,
            date_from: range.from,
            date_to: range.to,
            search: debouncedSearch || undefined,
            dataset,
            disabled_warehouses: Array.from(disabledWarehouses),
          },
        },
      );
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `logistics_${dataset}_${activeId}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } finally {
      setExportingDataset(null);
    }
  };

  return (
    <PageShell>
      <PageHeader
        title="Логистика WB"
        description="Рабочее место продавца: куда везти, сколько отгружать, где теряются деньги и какие WB-источники закрывают расчёт."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => range.setPreset(7)}
            >
              <CalendarDays className="h-4 w-4" />7 дней
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => range.setPreset(30)}
            >
              <CalendarDays className="h-4 w-4" />
              30 дней
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => query.refetch()}
              disabled={!activeId || query.isFetching}
            >
              <RefreshCw
                className={cn("h-4 w-4", query.isFetching && "animate-spin")}
              />
              Обновить
            </Button>
          </div>
        }
      />

      {!activeId && <NoAccountSelected />}

      {activeId && (
        <DataDependencyNotice
          accountId={activeId}
          domains={[
            "stocks",
            "supplies",
            "tariffs",
            "orders",
            "sales",
            "finance",
            "analytics",
            "logistics",
          ]}
        />
      )}

      {activeId && (
        <div className="space-y-4">
          <LogisticsCommandBar
            search={search}
            onSearch={setSearch}
            from={range.from}
            to={range.to}
            generatedAt={data?.generated_at}
          />

          {query.isLoading && <LogisticsSkeleton />}

          {query.isError && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Не удалось загрузить логистику</AlertTitle>
              <AlertDescription className="mt-2 flex flex-col gap-2">
                <span>{(query.error as Error).message}</span>
                <Button
                  size="sm"
                  variant="outline"
                  className="w-fit"
                  onClick={() => query.refetch()}
                >
                  Повторить
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {hasUnexpectedPayload && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Некорректный ответ модуля логистики</AlertTitle>
              <AlertDescription>
                Сервер вернул данные без обязательных полей. Проверьте маршрут
                `/portal/logistics/overview` и повторите синхронизацию.
              </AlertDescription>
            </Alert>
          )}

          {data && (
            <>
              <LogisticsKpiStrip kpis={data.kpis} />

              <RecommendationsPanel
                recommendations={data.recommendations}
                tasks={visibleTasks}
                warehouses={warehouses}
                periodDays={periodDays}
                onSelectWarehouse={setSelectedWarehouseName}
              />

              <Tabs defaultValue="plan" className="w-full">
                <TabsList className="h-auto w-full justify-start overflow-x-auto rounded-md border bg-background p-1">
                  <TabsTrigger value="plan" className="gap-2 text-xs">
                    <ClipboardList className="h-3.5 w-3.5" />
                    План
                  </TabsTrigger>
                  <TabsTrigger value="shipment" className="gap-2 text-xs">
                    <PackagePlus className="h-3.5 w-3.5" />
                    Подсортировка
                  </TabsTrigger>
                  <TabsTrigger value="warehouses" className="gap-2 text-xs">
                    <Warehouse className="h-3.5 w-3.5" />
                    Склады
                  </TabsTrigger>
                  <TabsTrigger value="supplies" className="gap-2 text-xs">
                    <Factory className="h-3.5 w-3.5" />
                    Поставки
                  </TabsTrigger>
                  <TabsTrigger value="details" className="gap-2 text-xs">
                    <Database className="h-3.5 w-3.5" />
                    Расходы и API
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="plan" className="mt-4">
                  <DecisionDesk
                    tasks={visibleTasks}
                    products={products}
                    warehouses={warehouses}
                    regionalShipments={regionalShipments}
                    selectedTask={selectedTask}
                    selectedWarehouse={selectedWarehouse}
                    selectedTaskId={selectedTask?.id ?? null}
                    selectedWarehouseName={
                      selectedWarehouse?.warehouse_name ?? null
                    }
                    periodDays={periodDays}
                    onSelectTask={(task) => {
                      setSelectedTaskId(task.id);
                      if (task.warehouse_name) {
                        setSelectedWarehouseName(task.warehouse_name);
                      }
                    }}
                    onSelectWarehouse={setSelectedWarehouseName}
                    onExportTasks={() => exportCsv("tasks")}
                    exportingTasks={exportingDataset === "tasks"}
                  />
                </TabsContent>

                <TabsContent value="shipment" className="mt-4">
                  <ShipmentBuilderWorkspace
                    warehouses={warehouses}
                    products={products}
                    supplies={data.supplies}
                    regionalShipments={regionalShipments}
                    periodDays={periodDays}
                    onSelectWarehouse={setSelectedWarehouseName}
                    onExport={() => exportCsv("shipment")}
                    exporting={exportingDataset === "shipment"}
                  />
                </TabsContent>

                <TabsContent value="warehouses" className="mt-4">
                  <WarehouseWorkspace
                    rows={warehouses}
                    supplies={data.supplies}
                    products={products}
                    controls={data.warehouse_controls ?? []}
                    disabledWarehouses={disabledWarehouses}
                    selectedWarehouse={selectedWarehouse}
                    selectedName={selectedWarehouse?.warehouse_name ?? null}
                    periodDays={periodDays}
                    onSelect={setSelectedWarehouseName}
                    onToggleWarehouse={toggleWarehouseTasks}
                    onExport={() => exportCsv("controls")}
                    exporting={exportingDataset === "controls"}
                  />
                </TabsContent>

                <TabsContent value="supplies" className="mt-4">
                  <SupplyWorkspace rows={data.supplies} />
                </TabsContent>

                <TabsContent value="details" className="mt-4">
                  <LogisticsDetailsWorkspace
                    paidStorage={data.paid_storage_details ?? []}
                    acceptance={data.acceptance_details ?? []}
                    transit={data.transit_tariffs ?? []}
                    sellerWarehouses={data.seller_warehouses ?? []}
                    sources={data.data_sources}
                    capabilities={data.api_capabilities}
                    onExport={exportCsv}
                    exportingDataset={exportingDataset}
                  />
                </TabsContent>
              </Tabs>
            </>
          )}
        </div>
      )}
    </PageShell>
  );
}

function LogisticsCommandBar({
  search,
  onSearch,
  from,
  to,
  generatedAt,
}: {
  search: string;
  onSearch: (value: string) => void;
  from: string;
  to: string;
  generatedAt?: string | null;
}) {
  return (
    <div className="grid gap-3 rounded-md border bg-card p-3 lg:grid-cols-[minmax(280px,1fr)_auto] lg:items-center">
      <label className="flex min-w-0 items-center gap-2 rounded-md border bg-background px-3 py-2">
        <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Найти склад, регион, артикул или бренд"
          className="h-8 border-0 bg-transparent px-0 shadow-none focus-visible:ring-0"
        />
      </label>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="outline" className="gap-1">
          <CalendarDays className="h-3.5 w-3.5" />
          {formatDate(from)} - {formatDate(to)}
        </Badge>
        {generatedAt && (
          <Badge variant="outline" className="gap-1">
            <Clock className="h-3.5 w-3.5" />
            {formatDateTime(generatedAt)}
          </Badge>
        )}
      </div>
    </div>
  );
}

function LogisticsSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-28 rounded-md" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)_390px]">
        <Skeleton className="h-[560px] rounded-md" />
        <Skeleton className="h-[560px] rounded-md" />
        <Skeleton className="h-[560px] rounded-md" />
      </div>
    </div>
  );
}

function LogisticsKpiStrip({ kpis }: { kpis: LogisticsKpis }) {
  const totalLogistics =
    kpis.logistics_cost +
    kpis.return_logistics_cost +
    kpis.storage_cost +
    kpis.acceptance_cost;
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <ExecutiveMetric
        title="Выручка WB"
        value={formatMoney(kpis.revenue)}
        detail={`${formatNumber(kpis.orders_qty)} заказов · выкуп ${formatPercent(kpis.buyout_percent)}`}
        icon={CircleDollarSign}
        tone="teal"
      />
      <ExecutiveMetric
        title="Логистика, хранение, приёмка"
        value={formatMoney(totalLogistics)}
        detail={`${formatPercent(kpis.logistics_share_percent)} от выручки · ${formatMoney(kpis.avg_logistics_per_order)} / заказ`}
        icon={Truck}
        tone="amber"
      />
      <ExecutiveMetric
        title="Потерянный спрос"
        value={formatMoney(kpis.missed_revenue)}
        detail={`${formatNumber(kpis.missed_orders_qty)} упущенных · отмен ${formatNumber(kpis.cancelled_orders_qty)}`}
        icon={XCircle}
        tone="red"
      />
      <ExecutiveMetric
        title="Запас и слоты"
        value={`${formatNumber(kpis.stock_units)} шт`}
        detail={`${formatNumber(kpis.active_warehouses)} складов · ${formatNumber(kpis.available_acceptance_slots)} слотов`}
        icon={Warehouse}
        tone="blue"
      />
    </div>
  );
}

function ExecutiveMetric({
  title,
  value,
  detail,
  icon: Icon,
  tone,
}: {
  title: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  tone: "teal" | "amber" | "red" | "blue";
}) {
  const toneClass = {
    teal: "border-teal-200 bg-teal-50 text-teal-700",
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    red: "border-red-200 bg-red-50 text-red-700",
    blue: "border-sky-200 bg-sky-50 text-sky-700",
  }[tone];
  return (
    <Card className="rounded-md">
      <CardContent className="flex h-full min-h-28 flex-col justify-between gap-3 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="truncate text-sm font-medium text-muted-foreground">
            {title}
          </div>
          <span
            className={cn(
              "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border",
              toneClass,
            )}
          >
            <Icon className="h-4 w-4" />
          </span>
        </div>
        <div className="min-w-0">
          <div className="truncate text-2xl font-semibold tracking-normal">
            {value}
          </div>
          <div className="mt-1 truncate text-xs text-muted-foreground">
            {detail}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function RecommendationsPanel({
  recommendations,
  tasks,
  warehouses,
  periodDays,
  onSelectWarehouse,
}: {
  recommendations: RecommendationRow[];
  tasks: LogisticsTaskRow[];
  warehouses: WarehouseRow[];
  periodDays: number;
  onSelectWarehouse: (name: string) => void;
}) {
  const topWarehouses = warehouses
    .filter((row) => row.risk_level !== "ok")
    .slice(0, 3);
  const fallbackItems = topWarehouses.map<RecommendationRow>((row) => {
    const calc = calculateWarehouse(row, periodDays);
    return {
      severity: row.risk_level,
      title: row.warehouse_name,
      detail:
        row.recommendation ||
        `Проверить запас: риск потери ${formatMoney(row.missed_revenue)}.`,
      action:
        calc.replenishmentQty > 0
          ? `К отгрузке +${formatNumber(calc.replenishmentQty)}`
          : "Открыть разбор",
    };
  });
  const seededItems = [
    ...recommendations,
    ...fallbackItems.filter(
      (fallback) =>
        !recommendations.some((item) => item.title === fallback.title),
    ),
  ];
  const items = seededItems
    .slice(0, 3)
    .map((item, index) => ({ ...item, id: `${item.title}-${index}` }));
  if (!items.length && !tasks.length) return null;

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="grid gap-3 md:grid-cols-3">
        {items.map((item, index) => (
          <button
            key={item.id}
            type="button"
            className={cn(
              "rounded-md border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-sm",
              severitySoftClass(item.severity),
            )}
            onClick={() => {
              const warehouse =
                warehouses.find((row) => row.warehouse_name === item.title) ||
                topWarehouses[index];
              if (warehouse) onSelectWarehouse(warehouse.warehouse_name);
            }}
          >
            <div className="mb-3 flex items-center justify-between gap-2">
              <RiskBadge level={item.severity} />
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="line-clamp-1 font-semibold">{item.title}</div>
            <div className="mt-1 line-clamp-2 text-sm text-muted-foreground">
              {item.detail}
            </div>
            <div className="mt-3 text-sm font-medium">{item.action}</div>
          </button>
        ))}
      </div>
      <Card className="rounded-md">
        <CardContent className="grid h-full content-between gap-3 p-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium">
              <ListChecks className="h-4 w-4 text-muted-foreground" />
              Очередь решений
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Сначала закрываем критичные склады, затем товары с максимальным
              чистым эффектом.
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center text-xs">
            <MiniCounter
              label="задач"
              value={formatNumber(tasks.length)}
              tone="neutral"
            />
            <MiniCounter
              label="критично"
              value={formatNumber(
                tasks.filter((task) => task.severity === "danger").length,
              )}
              tone="red"
            />
            <MiniCounter
              label="складов"
              value={formatNumber(topWarehouses.length)}
              tone="amber"
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function MiniCounter({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "neutral" | "red" | "amber";
}) {
  const toneClass = {
    neutral: "bg-muted text-foreground",
    red: "bg-red-50 text-red-700",
    amber: "bg-amber-50 text-amber-700",
  }[tone];
  return (
    <div className={cn("rounded-md px-2 py-2", toneClass)}>
      <div className="font-semibold">{value}</div>
      <div className="text-muted-foreground">{label}</div>
    </div>
  );
}

function DecisionDesk({
  tasks,
  products,
  warehouses,
  regionalShipments,
  selectedTask,
  selectedWarehouse,
  selectedTaskId,
  selectedWarehouseName,
  periodDays,
  onSelectTask,
  onSelectWarehouse,
  onExportTasks,
  exportingTasks,
}: {
  tasks: LogisticsTaskRow[];
  products: ProductRow[];
  warehouses: WarehouseRow[];
  regionalShipments: RegionalShipmentRow[];
  selectedTask: LogisticsTaskRow | null;
  selectedWarehouse: WarehouseRow | null;
  selectedTaskId: string | null;
  selectedWarehouseName: string | null;
  periodDays: number;
  onSelectTask: (task: LogisticsTaskRow) => void;
  onSelectWarehouse: (name: string) => void;
  onExportTasks: () => void;
  exportingTasks: boolean;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)] 2xl:grid-cols-[300px_minmax(0,1fr)_360px]">
      <div className="space-y-4 xl:self-start">
        <TaskQueuePanel
          tasks={tasks}
          selectedTaskId={selectedTaskId}
          onSelectTask={onSelectTask}
          onExport={onExportTasks}
          exporting={exportingTasks}
        />
        <DecisionFocusPanel
          tasks={tasks}
          warehouses={warehouses}
          regionalShipments={regionalShipments}
          periodDays={periodDays}
          onSelectWarehouse={onSelectWarehouse}
        />
      </div>
      <div className="space-y-4">
        <ShipmentBuilderWorkspace
          warehouses={warehouses}
          products={products}
          supplies={[]}
          regionalShipments={regionalShipments}
          periodDays={periodDays}
          onSelectWarehouse={onSelectWarehouse}
          compact
        />
        <div className="2xl:hidden">
          <InsightPanel
            task={selectedTask}
            warehouse={selectedWarehouse}
            products={products}
            selectedWarehouseName={selectedWarehouseName}
            periodDays={periodDays}
          />
        </div>
      </div>
      <div className="hidden 2xl:block">
        <InsightPanel
          task={selectedTask}
          warehouse={selectedWarehouse}
          products={products}
          selectedWarehouseName={selectedWarehouseName}
          periodDays={periodDays}
        />
      </div>
    </div>
  );
}

function DecisionFocusPanel({
  tasks,
  warehouses,
  regionalShipments,
  periodDays,
  onSelectWarehouse,
}: {
  tasks: LogisticsTaskRow[];
  warehouses: WarehouseRow[];
  regionalShipments: RegionalShipmentRow[];
  periodDays: number;
  onSelectWarehouse: (name: string) => void;
}) {
  const riskyWarehouses = warehouses
    .filter((row) => row.risk_level !== "ok")
    .slice()
    .sort(
      (a, b) =>
        riskWeight(a.risk_level) - riskWeight(b.risk_level) ||
        b.missed_revenue - a.missed_revenue,
    )
    .slice(0, 3);
  const taskByWarehouse = new Map(
    tasks
      .filter((task) => task.warehouse_name)
      .map((task) => [task.warehouse_name as string, task]),
  );
  const totalSupply = riskyWarehouses.reduce(
    (sum, row) =>
      sum +
      (taskByWarehouse.get(row.warehouse_name)?.recommended_supply_qty ??
        calculateWarehouse(row, periodDays).replenishmentQty),
    0,
  );
  const totalMissed = riskyWarehouses.reduce(
    (sum, row) => sum + row.missed_revenue,
    0,
  );
  const openSlots = warehouses.filter(
    (row) => row.allow_unload || row.acceptance_status === "available",
  ).length;
  const bestRoutes = regionalShipments
    .slice()
    .sort((a, b) => b.expected_net_effect - a.expected_net_effect)
    .slice(0, 2);

  return (
    <Card className="rounded-md">
      <CardHeader className="border-b p-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <RouteIcon className="h-4 w-4 text-muted-foreground" />
          Контроль маршрута
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-3">
        <div className="grid grid-cols-2 gap-2">
          <MiniCounter
            label="к довозу"
            value={`+${formatNumber(totalSupply)}`}
            tone="neutral"
          />
          <MiniCounter
            label="слотов"
            value={formatNumber(openSlots)}
            tone={openSlots ? "neutral" : "red"}
          />
        </div>
        <div className="rounded-md border bg-muted/20 p-3">
          <div className="text-xs text-muted-foreground">
            Потеря в зоне риска
          </div>
          <div className="mt-1 text-lg font-semibold">
            {formatMoney(totalMissed)}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Считается по складам с риском, без нормальных остатков.
          </div>
        </div>
        <div className="space-y-2">
          {riskyWarehouses.map((row) => {
            const task = taskByWarehouse.get(row.warehouse_name);
            const replenishmentQty =
              task?.recommended_supply_qty ??
              calculateWarehouse(row, periodDays).replenishmentQty;
            return (
              <button
                key={row.warehouse_name}
                type="button"
                onClick={() => onSelectWarehouse(row.warehouse_name)}
                className="grid w-full gap-2 rounded-md border px-3 py-2 text-left transition hover:bg-muted/60"
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-sm font-medium">
                    {row.warehouse_name}
                  </span>
                  <RiskBadge level={row.risk_level} />
                </span>
                <span className="grid grid-cols-2 gap-2 text-xs">
                  <MetricInline
                    label="Потеря"
                    value={formatMoney(row.missed_revenue)}
                  />
                  <MetricInline
                    label="Довоз"
                    value={`+${formatNumber(replenishmentQty)}`}
                  />
                </span>
              </button>
            );
          })}
        </div>
        {bestRoutes.length > 0 && (
          <div className="space-y-2 rounded-md border bg-background p-3">
            <div className="text-xs font-medium text-muted-foreground">
              Лучшие направления
            </div>
            {bestRoutes.map((route) => (
              <div
                key={route.id}
                className="flex items-start justify-between gap-3 text-xs"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">
                    {route.warehouse_name}
                  </span>
                  <span className="block truncate text-muted-foreground">
                    {route.reason}
                  </span>
                </span>
                <span className="shrink-0 font-semibold">
                  {formatMoney(route.expected_net_effect)}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function TaskQueuePanel({
  tasks,
  selectedTaskId,
  onSelectTask,
  onExport,
  exporting,
}: {
  tasks: LogisticsTaskRow[];
  selectedTaskId: string | null;
  onSelectTask: (task: LogisticsTaskRow) => void;
  onExport: () => void;
  exporting: boolean;
}) {
  if (!tasks.length) {
    return (
      <Alert className="rounded-md">
        <ClipboardList className="h-4 w-4" />
        <AlertTitle>Задач по логистике нет</AlertTitle>
        <AlertDescription>
          После появления дефицита, дорогой логистики или закрытой приёмки
          задачи появятся здесь.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <Card className="rounded-md">
      <CardHeader className="border-b p-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">Что сделать сейчас</CardTitle>
            <div className="mt-1 text-xs text-muted-foreground">
              {formatNumber(tasks.length)} задач по приоритету
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="gap-2"
            onClick={onExport}
            disabled={exporting}
          >
            <Download className="h-4 w-4" />
            CSV
          </Button>
        </div>
      </CardHeader>
      <CardContent className="max-h-[690px] space-y-2 overflow-y-auto p-3">
        {tasks.map((task) => (
          <button
            key={task.id}
            type="button"
            onClick={() => onSelectTask(task)}
            className={cn(
              "grid w-full gap-2 rounded-md border px-3 py-3 text-left transition hover:bg-muted/60",
              selectedTaskId === task.id && "border-primary bg-primary/5",
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="line-clamp-2 text-sm font-semibold">
                  {task.title}
                </div>
                <div className="mt-1 flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
                  <MapPin className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">
                    {task.warehouse_name || task.region_name || "общий контур"}
                  </span>
                </div>
              </div>
              <RiskBadge level={task.severity} />
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <MetricInline
                label="Потенциал"
                value={formatMoney(task.potential_revenue)}
              />
              <MetricInline
                label="К отгрузке"
                value={`+${formatNumber(task.recommended_supply_qty)}`}
              />
              <MetricInline
                label="Эффект"
                value={formatMoney(task.expected_net_effect)}
              />
            </div>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

function InsightPanel({
  task,
  warehouse,
  products,
  selectedWarehouseName,
  periodDays,
}: {
  task: LogisticsTaskRow | null;
  warehouse: WarehouseRow | null;
  products: ProductRow[];
  selectedWarehouseName: string | null;
  periodDays: number;
}) {
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const relatedProducts = task
    ? relatedProductsForTask(products, task)
    : selectedWarehouseName
      ? sortProductRows(
          products.filter(
            (product) => product.warehouse_name === selectedWarehouseName,
          ),
        ).slice(0, 12)
      : [];
  const calc = warehouse ? calculateWarehouse(warehouse, periodDays) : null;

  return (
    <>
      <Card className="rounded-md 2xl:sticky 2xl:top-20 2xl:self-start">
        <CardHeader className="border-b p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <CardTitle className="line-clamp-2 text-base">
                {task?.title || warehouse?.warehouse_name || "Детали"}
              </CardTitle>
              <div className="mt-1 truncate text-xs text-muted-foreground">
                {task?.warehouse_name ||
                  task?.region_name ||
                  warehouse?.region_name ||
                  "выберите задачу или склад"}
              </div>
            </div>
            {task ? (
              <RiskBadge level={task.severity} />
            ) : warehouse ? (
              <RiskBadge level={warehouse.risk_level} />
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-4">
          {task && (
            <Alert className={severitySoftClass(task.severity)}>
              <Gauge className="h-4 w-4" />
              <AlertTitle>Причина</AlertTitle>
              <AlertDescription className="mt-1">
                {task.detail}
              </AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-2 gap-3">
            <CompactFact
              label="Потенциал"
              value={formatMoney(
                task?.potential_revenue ?? warehouse?.missed_revenue,
              )}
              note={`${formatNumber(task?.potential_orders_qty ?? warehouse?.missed_orders_qty)} заказов`}
            />
            <CompactFact
              label="Чистый эффект"
              value={formatMoney(
                task?.expected_net_effect ?? calc?.marginAfterLogistics,
              )}
              note={task ? confidenceLabel(task.confidence) : "после логистики"}
            />
            <CompactFact
              label="К отгрузке"
              value={`+${formatNumber(task?.recommended_supply_qty ?? calc?.replenishmentQty)}`}
              note={`${FAST_REPLENISHMENT_DAYS} дн. покрытия`}
            />
            <CompactFact
              label="Логистика"
              value={formatPercent(
                task?.logistics_share_percent ??
                  warehouse?.logistics_share_percent,
              )}
              note={formatMoney(calc?.costPerOrder)}
            />
          </div>

          {task && (
            <div className="rounded-md border bg-muted/20 p-3">
              <div className="text-xs font-medium text-muted-foreground">
                Действие
              </div>
              <div className="mt-1 text-sm font-medium">{task.action}</div>
            </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2 text-sm font-medium">
              <span>Артикулы внутри</span>
              <Badge variant="outline">
                {formatNumber(relatedProducts.length)}
              </Badge>
            </div>
            <ProductMiniTable products={relatedProducts.slice(0, 6)} compact />
          </div>

          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
            <Button
              size="sm"
              className="gap-2"
              onClick={() => setAnalysisOpen(true)}
              disabled={!relatedProducts.length}
            >
              <Calculator className="h-4 w-4" />
              Показать расчёт
            </Button>
            <Button asChild size="sm" variant="outline" className="gap-2">
              <Link to="/stock-control">
                <PackagePlus className="h-4 w-4" />
                План поставки
                <ArrowUpRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
      <TaskAnalysisSheet
        task={task}
        products={relatedProducts}
        open={analysisOpen}
        onOpenChange={setAnalysisOpen}
      />
    </>
  );
}

function TaskAnalysisSheet({
  task,
  products,
  open,
  onOpenChange,
}: {
  task: LogisticsTaskRow | null;
  products: ProductRow[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const totals = products.reduce(
    (acc, row) => ({
      stock: acc.stock + row.stock_units,
      supply14: acc.supply14 + row.recommended_supply_14,
      supply30: acc.supply30 + row.recommended_supply_30,
      revenue: acc.revenue + row.potential_revenue,
      net: acc.net + row.expected_net_effect,
    }),
    { stock: 0, supply14: 0, supply30: 0, revenue: 0, net: 0 },
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col overflow-hidden p-0 sm:max-w-[min(1080px,calc(100vw-2rem))]">
        <div className="border-b px-5 py-4">
          <SheetHeader className="pr-8 text-left">
            <div className="flex flex-wrap items-center gap-2">
              {task && <RiskBadge level={task.severity} />}
              <Badge variant="outline" className="gap-1">
                <Calculator className="h-3.5 w-3.5" />
                расчёт поставки
              </Badge>
            </div>
            <SheetTitle className="break-words text-lg">
              {task?.title || "Расчёт по выбранным артикулам"}
            </SheetTitle>
            <SheetDescription>
              Считаем запас, план отгрузки, ожидаемую выручку и чистый эффект.
            </SheetDescription>
          </SheetHeader>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <CompactFact
                  label="Артикулы"
                  value={formatNumber(products.length)}
                  note="в расчёте"
                />
                <CompactFact
                  label="Остаток"
                  value={formatNumber(totals.stock)}
                  note="сейчас на складе"
                />
                <CompactFact
                  label="Поставка 30 дн."
                  value={`+${formatNumber(totals.supply30)}`}
                  note="плановый довоз"
                />
                <CompactFact
                  label="Чистый эффект"
                  value={formatMoney(task?.expected_net_effect ?? totals.net)}
                  note={confidenceLabel(task?.confidence || "medium")}
                />
              </div>
              <ProductMiniTable products={products.slice(0, 28)} />
            </div>

            <div className="space-y-3">
              <div className="rounded-md border bg-background p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium">
                  <Calculator className="h-4 w-4 text-muted-foreground" />
                  Формула
                </div>
                <div className="space-y-3 text-sm">
                  <FormulaLine
                    label="Цель запаса"
                    value="скорость продаж в день × выбранный горизонт"
                  />
                  <FormulaLine
                    label="Отгрузка"
                    value="max(цель − остаток, 0), затем кратность коробу"
                  />
                  <FormulaLine
                    label="Чистый эффект"
                    value="выручка поставки × маржа − логистика на продажу"
                  />
                </div>
              </div>
              {task && (
                <div className="rounded-md border bg-muted/20 p-4">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                    <ListChecks className="h-4 w-4 text-muted-foreground" />
                    Действие
                  </div>
                  <div className="text-sm">{task.action}</div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {task.tags.map((tag) => (
                      <Badge key={tag} variant="outline">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function ShipmentBuilderWorkspace({
  warehouses,
  products,
  supplies,
  regionalShipments,
  periodDays,
  onSelectWarehouse,
  onExport,
  exporting = false,
  compact = false,
}: {
  warehouses: WarehouseRow[];
  products: ProductRow[];
  supplies: SupplyRow[];
  regionalShipments: RegionalShipmentRow[];
  periodDays: number;
  onSelectWarehouse: (warehouseName: string) => void;
  onExport?: () => void;
  exporting?: boolean;
  compact?: boolean;
}) {
  const [mode, setMode] = useState<ShipmentBuilderMode>("warehouse");
  const [targetDays, setTargetDays] = useState(45);
  const [minQty, setMinQty] = useState(1);
  const [boxMultiple, setBoxMultiple] = useState(1);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [excludedIds, setExcludedIds] = useState<Set<string>>(() => new Set());
  const [sorting, setSorting] = useState<SortingState>([
    { id: "shipmentNet", desc: true },
  ]);

  const options = useMemo(() => {
    if (mode === "region") {
      const names = Array.from(
        new Set(
          warehouses
            .map((row) => row.region_name)
            .filter((name): name is string => Boolean(name)),
        ),
      );
      return names.length ? names : ["регион не определён"];
    }
    return warehouses.map((row) => row.warehouse_name);
  }, [mode, warehouses]);

  const effectiveKey =
    selectedKey && options.includes(selectedKey)
      ? selectedKey
      : options[0] || null;

  useEffect(() => {
    setSelectedKey(null);
    setExcludedIds(new Set());
  }, [mode]);

  const sourceProducts = useMemo(() => {
    if (!effectiveKey) return [];
    const filtered =
      mode === "region"
        ? products.filter(
            (row) =>
              (row.region_name || "регион не определён") === effectiveKey,
          )
        : products.filter((row) => row.warehouse_name === effectiveKey);
    return sortProductRows(filtered).slice(0, compact ? 60 : 120);
  }, [compact, effectiveKey, mode, products]);

  const shipmentRows = useMemo<ShipmentLine[]>(
    () =>
      sourceProducts.map((row) => {
        const targetStock = Math.ceil(row.avg_daily_sales * targetDays);
        const rawQty = Math.max(targetStock - row.stock_units, 0);
        const minApplied = rawQty > 0 ? Math.max(rawQty, minQty) : 0;
        const roundedQty =
          minApplied > 0
            ? Math.ceil(minApplied / Math.max(boxMultiple, 1)) *
              Math.max(boxMultiple, 1)
            : 0;
        const avgSaleValue = divide(row.revenue, row.sales_qty) || 0;
        const logisticsTotal =
          row.logistics_cost +
          row.return_logistics_cost +
          row.storage_cost +
          row.acceptance_cost;
        const logisticsPerSale = divide(logisticsTotal, row.sales_qty) || 0;
        const marginFactor =
          row.margin_percent == null
            ? 0.35
            : Math.max(row.margin_percent / 100, 0.05);
        const shipmentRevenue = roundedQty * avgSaleValue;
        const shipmentNet =
          shipmentRevenue * marginFactor - roundedQty * logisticsPerSale;
        return {
          ...row,
          selected: !excludedIds.has(row.id) && roundedQty > 0,
          targetStock,
          shipmentQty: roundedQty,
          shipmentRevenue,
          shipmentNet,
        };
      }),
    [boxMultiple, excludedIds, minQty, sourceProducts, targetDays],
  );

  const visibleLines = useMemo(
    () =>
      shipmentRows.filter(
        (row) => row.shipmentQty > 0 || row.risk_level !== "ok",
      ),
    [shipmentRows],
  );
  const selectedLines = useMemo(
    () => shipmentRows.filter((row) => row.selected),
    [shipmentRows],
  );
  const totals = selectedLines.reduce(
    (acc, row) => ({
      sku: acc.sku + 1,
      qty: acc.qty + row.shipmentQty,
      revenue: acc.revenue + row.shipmentRevenue,
      net: acc.net + row.shipmentNet,
    }),
    { sku: 0, qty: 0, revenue: 0, net: 0 },
  );

  const toggleLine = useCallback((id: string, checked: boolean) => {
    setExcludedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const columns = useMemo<ColumnDef<ShipmentLine>[]>(
    () => [
      {
        id: "selected",
        enableSorting: false,
        header: "",
        cell: ({ row }) => (
          <Checkbox
            checked={row.original.selected}
            disabled={row.original.shipmentQty <= 0}
            onCheckedChange={(checked) =>
              toggleLine(row.original.id, checked === true)
            }
            aria-label={`Включить ${productLabel(row.original)}`}
          />
        ),
      },
      {
        id: "product",
        accessorFn: (row) => productLabel(row),
        header: ({ column }) => (
          <SortableHeader column={column} label="Артикул" />
        ),
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="truncate font-medium">
              {productLabel(row.original)}
            </div>
            <div className="truncate text-xs text-muted-foreground">
              WB {row.original.nm_id ?? "—"} · {row.original.brand || "бренд —"}
            </div>
          </div>
        ),
      },
      {
        id: "risk",
        accessorFn: (row) => riskWeight(row.risk_level),
        header: ({ column }) => <SortableHeader column={column} label="Риск" />,
        cell: ({ row }) => <RiskBadge level={row.original.risk_level} />,
      },
      {
        id: "stock_units",
        accessorFn: (row) => row.stock_units,
        header: ({ column }) => (
          <SortableHeader column={column} label="Остаток" align="right" />
        ),
        cell: ({ row }) => (
          <NumberCell
            value={formatNumber(row.original.stock_units)}
            note={
              row.original.turnover_days
                ? `${formatNumber(row.original.turnover_days)} дн.`
                : "нет покрытия"
            }
          />
        ),
      },
      {
        id: "avg_daily_sales",
        accessorFn: (row) => row.avg_daily_sales,
        header: ({ column }) => (
          <SortableHeader column={column} label="Скорость" align="right" />
        ),
        cell: ({ row }) => (
          <NumberCell
            value={formatNumber(row.original.avg_daily_sales)}
            note="шт / день"
          />
        ),
      },
      {
        id: "targetStock",
        accessorFn: (row) => row.targetStock,
        header: ({ column }) => (
          <SortableHeader column={column} label="Цель" align="right" />
        ),
        cell: ({ row }) => (
          <NumberCell
            value={formatNumber(row.original.targetStock)}
            note={`${targetDays} дн.`}
          />
        ),
      },
      {
        id: "shipmentQty",
        accessorFn: (row) => row.shipmentQty,
        header: ({ column }) => (
          <SortableHeader column={column} label="Отгрузка" align="right" />
        ),
        cell: ({ row }) => (
          <NumberCell
            value={`+${formatNumber(row.original.shipmentQty)}`}
            note={row.original.selected ? "включено" : "исключено"}
            strong
          />
        ),
      },
      {
        id: "shipmentNet",
        accessorFn: (row) => row.shipmentNet,
        header: ({ column }) => (
          <SortableHeader column={column} label="Чистый эффект" align="right" />
        ),
        cell: ({ row }) => (
          <NumberCell
            value={formatMoney(row.original.shipmentNet)}
            note={formatMoney(row.original.shipmentRevenue)}
            strong
          />
        ),
      },
    ],
    [targetDays, toggleLine],
  );

  const table = useReactTable({
    data: visibleLines,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const sortedRows = table.getRowModel().rows.map((row) => row.original);

  const chartRows = selectedLines
    .slice()
    .sort((a, b) => b.shipmentNet - a.shipmentNet)
    .slice(0, compact ? 5 : 8)
    .map((row) => ({
      name: compactProduct(productLabel(row)),
      qty: row.shipmentQty,
      effect: Math.round(row.shipmentNet),
      risk: row.risk_level,
    }));

  const relatedSupplies = supplies
    .filter((supply) =>
      mode === "region"
        ? warehouses.some(
            (row) =>
              row.region_name === effectiveKey &&
              [supply.actual_warehouse_name, supply.warehouse_name].includes(
                row.warehouse_name,
              ),
          )
        : [supply.actual_warehouse_name, supply.warehouse_name].includes(
            effectiveKey || "",
          ),
    )
    .slice(0, 4);

  if (!products.length) {
    return (
      <Alert className="rounded-md">
        <PackageSearch className="h-4 w-4" />
        <AlertTitle>Данных по артикулам пока нет</AlertTitle>
        <AlertDescription>
          После синхронизации заказов, продаж, финансов и остатков здесь
          появится подсортировка на уровне товара.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div
      className={cn(
        "grid gap-4",
        !compact && "xl:grid-cols-[280px_minmax(0,1fr)_330px]",
      )}
    >
      {!compact && (
        <DirectionPanel
          mode={mode}
          onModeChange={setMode}
          options={options}
          selected={effectiveKey}
          onSelect={(option) => {
            setSelectedKey(option);
            if (mode === "warehouse") onSelectWarehouse(option);
          }}
        />
      )}

      <Card className="self-start rounded-md">
        <CardHeader className="border-b p-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle className="text-base">
                  Подсортировка по выгоде
                </CardTitle>
                <Badge variant="outline">
                  {effectiveKey || "направление —"}
                </Badge>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                Сортируйте по остатку, скорости, цели, отгрузке и чистому
                эффекту. Технические поля скрыты, оставлены рабочие показатели.
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {onExport && (
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-2"
                  onClick={onExport}
                  disabled={exporting}
                >
                  <Download className="h-4 w-4" />
                  Экспорт
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="grid gap-0 border-b md:grid-cols-4 md:divide-x">
            <DetailStat
              label="Артикулов выбрано"
              value={formatNumber(totals.sku)}
              icon={FileSpreadsheet}
            />
            <DetailStat
              label="К отгрузке"
              value={`+${formatNumber(totals.qty)}`}
              icon={PackagePlus}
            />
            <DetailStat
              label="Потенциал"
              value={formatMoney(totals.revenue)}
              icon={CircleDollarSign}
            />
            <DetailStat
              label="Чистый эффект"
              value={formatMoney(totals.net)}
              icon={Target}
            />
          </div>

          {compact && (
            <div className="grid gap-3 border-b p-3 lg:grid-cols-[1fr_260px]">
              <CompactDirectionPicker
                options={options}
                selected={effectiveKey}
                mode={mode}
                onModeChange={setMode}
                onSelect={(option) => {
                  setSelectedKey(option);
                  if (mode === "warehouse") onSelectWarehouse(option);
                }}
              />
              <ShipmentSettings
                targetDays={targetDays}
                minQty={minQty}
                boxMultiple={boxMultiple}
                onTargetDays={setTargetDays}
                onMinQty={setMinQty}
                onBoxMultiple={setBoxMultiple}
                compact
              />
            </div>
          )}

          <ShipmentTable
            table={table}
            rows={sortedRows}
            toggleLine={toggleLine}
          />
        </CardContent>
      </Card>

      {!compact && (
        <div className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          <ShipmentSettings
            targetDays={targetDays}
            minQty={minQty}
            boxMultiple={boxMultiple}
            onTargetDays={setTargetDays}
            onMinQty={setMinQty}
            onBoxMultiple={setBoxMultiple}
          />
          <ShipmentChart rows={chartRows} />
          <SuppliesInWay rows={relatedSupplies} />
        </div>
      )}
    </div>
  );
}

function DirectionPanel({
  mode,
  onModeChange,
  options,
  selected,
  onSelect,
}: {
  mode: ShipmentBuilderMode;
  onModeChange: (mode: ShipmentBuilderMode) => void;
  options: string[];
  selected: string | null;
  onSelect: (option: string) => void;
}) {
  return (
    <Card className="rounded-md xl:sticky xl:top-20 xl:self-start">
      <CardHeader className="border-b p-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <RouteIcon className="h-4 w-4" />
          Направления
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-3">
        <div className="grid grid-cols-2 gap-1 rounded-md bg-muted p-1">
          <Button
            size="sm"
            variant={mode === "warehouse" ? "default" : "ghost"}
            className="h-8 gap-2"
            onClick={() => onModeChange("warehouse")}
          >
            <Warehouse className="h-4 w-4" />
            Склад
          </Button>
          <Button
            size="sm"
            variant={mode === "region" ? "default" : "ghost"}
            className="h-8 gap-2"
            onClick={() => onModeChange("region")}
          >
            <MapPin className="h-4 w-4" />
            Регион
          </Button>
        </div>
        <div className="max-h-[590px] space-y-2 overflow-y-auto">
          {options.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => onSelect(option)}
              className={cn(
                "flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left text-sm transition hover:bg-muted/60",
                option === selected && "border-primary bg-primary/5",
              )}
            >
              <span className="min-w-0 truncate">{option}</span>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function CompactDirectionPicker({
  options,
  selected,
  mode,
  onModeChange,
  onSelect,
}: {
  options: string[];
  selected: string | null;
  mode: ShipmentBuilderMode;
  onModeChange: (mode: ShipmentBuilderMode) => void;
  onSelect: (option: string) => void;
}) {
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap gap-1 rounded-md bg-muted p-1">
        <Button
          size="sm"
          variant={mode === "warehouse" ? "default" : "ghost"}
          className="h-8 gap-2"
          onClick={() => onModeChange("warehouse")}
        >
          <Warehouse className="h-4 w-4" />
          Склад
        </Button>
        <Button
          size="sm"
          variant={mode === "region" ? "default" : "ghost"}
          className="h-8 gap-2"
          onClick={() => onModeChange("region")}
        >
          <MapPin className="h-4 w-4" />
          Регион
        </Button>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {options.slice(0, 12).map((option) => (
          <Button
            key={option}
            size="sm"
            variant={option === selected ? "default" : "outline"}
            className="h-8 shrink-0"
            onClick={() => onSelect(option)}
          >
            {option}
          </Button>
        ))}
      </div>
    </div>
  );
}

function ShipmentSettings({
  targetDays,
  minQty,
  boxMultiple,
  onTargetDays,
  onMinQty,
  onBoxMultiple,
  compact = false,
}: {
  targetDays: number;
  minQty: number;
  boxMultiple: number;
  onTargetDays: (value: number) => void;
  onMinQty: (value: number) => void;
  onBoxMultiple: (value: number) => void;
  compact?: boolean;
}) {
  const body = (
    <>
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="font-medium">Горизонт запаса</span>
          <Badge variant="outline">{targetDays} дней</Badge>
        </div>
        <Slider
          min={28}
          max={90}
          step={1}
          value={[targetDays]}
          onValueChange={(value) => onTargetDays(value[0] ?? 45)}
        />
        <div className="flex justify-between text-[11px] text-muted-foreground">
          <span>28</span>
          <span>60</span>
          <span>90</span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1 text-xs">
          <span className="text-muted-foreground">Мин. отгрузка</span>
          <Input
            type="number"
            min={1}
            value={minQty}
            onChange={(event) =>
              onMinQty(Math.max(Number(event.target.value) || 1, 1))
            }
            className="h-8"
          />
        </label>
        <label className="space-y-1 text-xs">
          <span className="text-muted-foreground">Кратность</span>
          <Input
            type="number"
            min={1}
            value={boxMultiple}
            onChange={(event) =>
              onBoxMultiple(Math.max(Number(event.target.value) || 1, 1))
            }
            className="h-8"
          />
        </label>
      </div>
    </>
  );
  if (compact) return <div className="space-y-3">{body}</div>;
  return (
    <Card className="rounded-md">
      <CardHeader className="border-b p-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <Settings2 className="h-4 w-4" />
          Настройки расчёта
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-4">{body}</CardContent>
    </Card>
  );
}

function ShipmentTable({
  table,
  rows,
  toggleLine,
}: {
  table: ReactTableInstance<ShipmentLine>;
  rows: ShipmentLine[];
  toggleLine: (id: string, checked: boolean) => void;
}) {
  return (
    <>
      <div className="divide-y md:hidden">
        {rows.map((row) => (
          <ShipmentLineCard
            key={row.id}
            row={row}
            checked={row.selected}
            onCheckedChange={(checked) => toggleLine(row.id, checked)}
          />
        ))}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    className={cn(
                      header.id === "selected" && "w-9",
                      header.id === "product" && "min-w-[220px]",
                      header.id === "risk" && "w-[96px]",
                      [
                        "stock_units",
                        "avg_daily_sales",
                        "targetStock",
                        "shipmentQty",
                        "shipmentNet",
                      ].includes(header.id) && "w-[116px] text-right",
                    )}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell
                    key={cell.id}
                    className={cn(
                      cell.column.id === "selected" && "w-9",
                      cell.column.id === "product" && "min-w-[220px]",
                      cell.column.id === "risk" && "w-[96px]",
                      [
                        "stock_units",
                        "avg_daily_sales",
                        "targetStock",
                        "shipmentQty",
                        "shipmentNet",
                      ].includes(cell.column.id) && "w-[116px] text-right",
                    )}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}

function ShipmentLineCard({
  row,
  checked,
  onCheckedChange,
}: {
  row: ShipmentLine;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="grid gap-3 px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2">
          <Checkbox
            checked={checked}
            disabled={row.shipmentQty <= 0}
            onCheckedChange={(value) => onCheckedChange(value === true)}
            aria-label={`Включить ${productLabel(row)}`}
            className="mt-0.5"
          />
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">
              {productLabel(row)}
            </div>
            <div className="truncate text-xs text-muted-foreground">
              {row.warehouse_name} · WB {row.nm_id ?? "—"}
            </div>
          </div>
        </div>
        <RiskBadge level={row.risk_level} />
      </div>
      <div className="grid grid-cols-4 gap-2 text-xs">
        <MetricInline label="Остаток" value={formatNumber(row.stock_units)} />
        <MetricInline
          label="Скорость"
          value={formatNumber(row.avg_daily_sales)}
        />
        <MetricInline
          label="Отгрузка"
          value={`+${formatNumber(row.shipmentQty)}`}
        />
        <MetricInline label="Эффект" value={formatMoney(row.shipmentNet)} />
      </div>
    </div>
  );
}

function ShipmentChart({
  rows,
}: {
  rows: { name: string; qty: number; effect: number; risk: string }[];
}) {
  if (!rows.length) {
    return (
      <Alert className="rounded-md">
        <PackagePlus className="h-4 w-4" />
        <AlertTitle>Нет позиций к отгрузке</AlertTitle>
        <AlertDescription>
          Измените горизонт запаса или выберите другое направление.
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <Card className="rounded-md">
      <CardHeader className="border-b p-4">
        <CardTitle className="text-base">Топ по чистому эффекту</CardTitle>
      </CardHeader>
      <CardContent className="p-4">
        <div className="h-[250px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={rows}
              layout="vertical"
              margin={{ left: 0, right: 16, top: 4, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                type="number"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11 }}
              />
              <YAxis
                dataKey="name"
                type="category"
                width={108}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11 }}
              />
              <RechartsTooltip
                formatter={(value: number, name: string) => [
                  name === "effect" ? formatMoney(value) : formatNumber(value),
                  name === "effect" ? "Чистый эффект" : "Отгрузка",
                ]}
              />
              <Bar dataKey="effect" radius={[0, 4, 4, 0]}>
                {rows.map((entry, index) => (
                  <Cell
                    key={`effect-${index}`}
                    fill={
                      entry.risk === "danger"
                        ? "#ef4444"
                        : entry.risk === "warning"
                          ? "#f97316"
                          : "#0f766e"
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function SuppliesInWay({ rows }: { rows: SupplyRow[] }) {
  if (!rows.length) return null;
  return (
    <Card className="rounded-md">
      <CardHeader className="border-b p-4">
        <CardTitle className="text-base">Поставки в пути</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 p-3">
        {rows.map((supply) => (
          <div
            key={supply.supply_id}
            className="grid grid-cols-[1fr_auto] gap-3 rounded-md border px-3 py-2 text-sm"
          >
            <span className="min-w-0">
              <span className="block truncate font-medium">
                #{supply.supply_id}
              </span>
              <span className="block truncate text-xs text-muted-foreground">
                {supply.status_label}
              </span>
            </span>
            <span className="text-right text-xs">
              <span className="block font-medium">
                {formatNumber(supply.accepted_qty)}/
                {formatNumber(supply.planned_qty)}
              </span>
              <span className="block text-muted-foreground">
                разница {formatNumber(supply.gap_qty)}
              </span>
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function WarehouseWorkspace({
  rows,
  supplies,
  products,
  controls,
  disabledWarehouses,
  selectedWarehouse,
  selectedName,
  periodDays,
  onSelect,
  onToggleWarehouse,
  onExport,
  exporting,
}: {
  rows: WarehouseRow[];
  supplies: SupplyRow[];
  products: ProductRow[];
  controls: WarehouseControlRow[];
  disabledWarehouses: Set<string>;
  selectedWarehouse: WarehouseRow | null;
  selectedName: string | null;
  periodDays: number;
  onSelect: (name: string) => void;
  onToggleWarehouse: (name: string) => void;
  onExport: () => void;
  exporting: boolean;
}) {
  const [deepWarehouse, setDeepWarehouse] = useState<WarehouseRow | null>(null);
  if (!rows.length) {
    return (
      <Alert className="rounded-md">
        <PackageSearch className="h-4 w-4" />
        <AlertTitle>Складов пока нет</AlertTitle>
        <AlertDescription>
          После синхронизации остатков, заказов, продаж и тарифов появится карта
          складской экономики.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
        <div className="space-y-4">
          <WarehouseControlsPanel
            rows={controls}
            disabledWarehouses={disabledWarehouses}
            onToggleWarehouse={onToggleWarehouse}
            onExport={onExport}
            exporting={exporting}
          />
          <WarehouseTable
            rows={rows}
            selectedName={selectedName}
            periodDays={periodDays}
            onSelect={onSelect}
            onOpen={setDeepWarehouse}
          />
        </div>
        {selectedWarehouse && (
          <WarehouseSidePanel
            row={selectedWarehouse}
            supplies={supplies}
            products={products.filter(
              (product) =>
                product.warehouse_name === selectedWarehouse.warehouse_name,
            )}
            periodDays={periodDays}
            onOpen={() => setDeepWarehouse(selectedWarehouse)}
          />
        )}
      </div>
      <WarehouseDeepDiveSheet
        row={deepWarehouse}
        supplies={supplies}
        products={products.filter(
          (product) => product.warehouse_name === deepWarehouse?.warehouse_name,
        )}
        periodDays={periodDays}
        open={Boolean(deepWarehouse)}
        onOpenChange={(open) => {
          if (!open) setDeepWarehouse(null);
        }}
      />
    </>
  );
}

function WarehouseControlsPanel({
  rows,
  disabledWarehouses,
  onToggleWarehouse,
  onExport,
  exporting,
}: {
  rows: WarehouseControlRow[];
  disabledWarehouses: Set<string>;
  onToggleWarehouse: (name: string) => void;
  onExport: () => void;
  exporting: boolean;
}) {
  if (!rows.length) return null;
  return (
    <Card className="rounded-md">
      <CardHeader className="border-b p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">Управление складами</CardTitle>
            <div className="mt-1 text-xs text-muted-foreground">
              Отключённые склады не участвуют в локальных задачах и
              подсортировке.
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="gap-2"
            onClick={onExport}
            disabled={exporting}
          >
            <Download className="h-4 w-4" />
            CSV
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-0 p-0 md:grid-cols-2 xl:grid-cols-4">
        {rows.slice(0, 8).map((row) => {
          const enabled = !disabledWarehouses.has(row.warehouse_name);
          return (
            <div
              key={row.warehouse_name}
              className="grid gap-3 border-b px-4 py-3 md:border-r"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">
                    {row.warehouse_name}
                  </span>
                  <WarehouseModeBadge mode={row.recommended_mode} />
                </div>
                <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                  {row.reason || "Склад в рабочем контуре."}
                </div>
              </div>
              <div className="flex items-center justify-between gap-3">
                <div className="flex flex-wrap gap-1">
                  <Badge variant="outline">
                    {formatNumber(row.task_count)} задач
                  </Badge>
                  <StatusBadge status={row.acceptance_status} />
                </div>
                <Switch
                  checked={enabled}
                  onCheckedChange={() => onToggleWarehouse(row.warehouse_name)}
                  aria-label={`Переключить склад ${row.warehouse_name}`}
                />
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function WarehouseTable({
  rows,
  selectedName,
  periodDays,
  onSelect,
  onOpen,
}: {
  rows: WarehouseRow[];
  selectedName: string | null;
  periodDays: number;
  onSelect: (name: string) => void;
  onOpen: (row: WarehouseRow) => void;
}) {
  return (
    <Card className="rounded-md">
      <CardHeader className="border-b p-4">
        <CardTitle className="text-base">
          Склады, маржа и потерянные заказы
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="divide-y md:hidden">
          {rows.map((row) => {
            const calc = calculateWarehouse(row, periodDays);
            return (
              <button
                key={row.warehouse_name}
                type="button"
                onClick={() => onSelect(row.warehouse_name)}
                className={cn(
                  "grid w-full gap-3 px-3 py-3 text-left transition hover:bg-muted/50",
                  row.warehouse_name === selectedName && "bg-primary/5",
                )}
              >
                <span className="flex items-start justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {row.warehouse_name}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {row.region_name || "регион не определён"}
                    </span>
                  </span>
                  <RiskBadge level={row.risk_level} />
                </span>
                <span className="grid grid-cols-3 gap-2 text-xs">
                  <MetricInline
                    label="Остаток"
                    value={formatNumber(row.stock_units)}
                  />
                  <MetricInline
                    label="Потеря"
                    value={formatMoney(row.missed_revenue)}
                  />
                  <MetricInline
                    label="План"
                    value={`+${formatNumber(calc.replenishmentQty)}`}
                  />
                </span>
              </button>
            );
          })}
        </div>
        <div className="hidden overflow-x-auto md:block">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-[220px]">Склад</TableHead>
                <TableHead>Риск</TableHead>
                <TableHead className="text-right">Остаток</TableHead>
                <TableHead className="text-right">Заказы</TableHead>
                <TableHead className="text-right">Выручка</TableHead>
                <TableHead className="text-right">Логистика</TableHead>
                <TableHead className="text-right">Маржа</TableHead>
                <TableHead className="text-right">Потеря</TableHead>
                <TableHead className="text-right">План</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => {
                const calc = calculateWarehouse(row, periodDays);
                const selected = row.warehouse_name === selectedName;
                return (
                  <TableRow
                    key={row.warehouse_name}
                    tabIndex={0}
                    aria-selected={selected}
                    onClick={() => onSelect(row.warehouse_name)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelect(row.warehouse_name);
                      }
                    }}
                    className={cn(
                      "cursor-pointer transition hover:bg-muted/50",
                      selected && "bg-primary/5 hover:bg-primary/10",
                    )}
                  >
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Warehouse className="h-4 w-4 text-muted-foreground" />
                        <div className="min-w-0">
                          <div className="truncate font-medium">
                            {row.warehouse_name}
                          </div>
                          <div className="truncate text-xs text-muted-foreground">
                            {row.region_name || "регион не определён"}
                          </div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <RiskBadge level={row.risk_level} />
                    </TableCell>
                    <TableCell className="text-right">
                      <NumberCell
                        value={formatNumber(row.stock_units)}
                        note={
                          row.turnover_days
                            ? `${formatNumber(row.turnover_days)} дн.`
                            : "—"
                        }
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <NumberCell
                        value={formatNumber(row.orders_qty)}
                        note={`−${formatNumber(row.missed_orders_qty)}`}
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <NumberCell
                        value={formatMoney(row.revenue)}
                        note={`выкуп ${formatPercent(row.buyout_percent)}`}
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <NumberCell
                        value={formatMoney(calc.totalLogistics)}
                        note={`${formatMoney(calc.costPerOrder)} / заказ`}
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <NumberCell
                        value={formatPercent(row.margin_percent)}
                        note={formatMoney(calc.marginAfterLogistics)}
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <NumberCell
                        value={formatMoney(row.missed_revenue)}
                        note={`${formatNumber(row.cancelled_orders_qty)} отмен`}
                        strong
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <NumberCell
                        value={`+${formatNumber(calc.replenishmentQty)}`}
                        note={`${FAST_REPLENISHMENT_DAYS} дн.`}
                        strong
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={(event) => {
                          event.stopPropagation();
                          onOpen(row);
                        }}
                        aria-label={`Открыть ${row.warehouse_name}`}
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

function WarehouseSidePanel({
  row,
  supplies,
  products,
  periodDays,
  onOpen,
}: {
  row: WarehouseRow;
  supplies: SupplyRow[];
  products: ProductRow[];
  periodDays: number;
  onOpen: () => void;
}) {
  const calc = calculateWarehouse(row, periodDays);
  const relatedSupplies = supplies
    .filter((supply) =>
      [supply.actual_warehouse_name, supply.warehouse_name].some(
        (name) => name && name === row.warehouse_name,
      ),
    )
    .slice(0, 3);

  return (
    <Card className="rounded-md xl:sticky xl:top-20 xl:self-start">
      <CardHeader className="border-b p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="truncate text-base">
              {row.warehouse_name}
            </CardTitle>
            <div className="mt-1 truncate text-xs text-muted-foreground">
              {row.region_name || "регион не определён"}
            </div>
          </div>
          <RiskBadge level={row.risk_level} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-muted-foreground">Покрытие остатка</span>
            <span className="font-medium">
              {row.turnover_days
                ? `${formatNumber(row.turnover_days)} дн.`
                : "—"}
            </span>
          </div>
          <Progress value={calc.stockCoveragePercent} className="h-2" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <CompactFact
            label="Потеря"
            value={formatMoney(row.missed_revenue)}
            note={`${formatNumber(row.missed_orders_qty)} заказов`}
          />
          <CompactFact
            label="К отгрузке"
            value={`+${formatNumber(calc.replenishmentQty)}`}
            note={`${FAST_REPLENISHMENT_DAYS} дн.`}
          />
          <CompactFact
            label="Лог/заказ"
            value={formatMoney(calc.costPerOrder)}
            note={formatPercent(row.logistics_share_percent)}
          />
          <CompactFact
            label="Приёмка"
            value={acceptanceLabel(row.acceptance_status)}
            note={`k=${row.acceptance_coefficient ?? "—"}`}
          />
        </div>
        <Alert className={severitySoftClass(row.risk_level)}>
          <Gauge className="h-4 w-4" />
          <AlertTitle>{calc.priority}</AlertTitle>
          <AlertDescription className="mt-1 text-sm">
            {row.recommendation ||
              "Склад держит нормальный запас и приемлемую стоимость логистики."}
          </AlertDescription>
        </Alert>
        <ProductMiniTable
          products={sortProductRows(products).slice(0, 6)}
          compact
        />
        {relatedSupplies.length > 0 && <SuppliesInWay rows={relatedSupplies} />}
        <Button size="sm" className="w-full gap-2" onClick={onOpen}>
          <Layers3 className="h-4 w-4" />
          Открыть полный разбор
        </Button>
      </CardContent>
    </Card>
  );
}

function WarehouseDeepDiveSheet({
  row,
  supplies,
  products,
  periodDays,
  open,
  onOpenChange,
}: {
  row: WarehouseRow | null;
  supplies: SupplyRow[];
  products: ProductRow[];
  periodDays: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const calc = row ? calculateWarehouse(row, periodDays) : null;
  const relatedSupplies = row
    ? supplies.filter((supply) =>
        [supply.actual_warehouse_name, supply.warehouse_name].some(
          (name) => name && name === row.warehouse_name,
        ),
      )
    : [];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col overflow-hidden p-0 sm:max-w-[min(1120px,calc(100vw-2rem))]">
        <div className="border-b px-5 py-4">
          <SheetHeader className="pr-8 text-left">
            <div className="flex flex-wrap items-center gap-2">
              {row && <RiskBadge level={row.risk_level} />}
              <Badge variant="outline">детальный склад</Badge>
            </div>
            <SheetTitle>{row?.warehouse_name || "Склад"}</SheetTitle>
            <SheetDescription>
              {row?.region_name || "регион не определён"}
            </SheetDescription>
          </SheetHeader>
        </div>
        {row && calc && (
          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            <Tabs defaultValue="money">
              <TabsList className="h-auto flex-wrap">
                <TabsTrigger value="money" className="text-xs">
                  Деньги
                </TabsTrigger>
                <TabsTrigger value="stock" className="text-xs">
                  Остатки
                </TabsTrigger>
                <TabsTrigger value="sku" className="text-xs">
                  Артикулы
                </TabsTrigger>
                <TabsTrigger value="acceptance" className="text-xs">
                  Приёмка
                </TabsTrigger>
                <TabsTrigger value="plan" className="text-xs">
                  План
                </TabsTrigger>
              </TabsList>
              <TabsContent
                value="money"
                className="mt-4 grid gap-4 lg:grid-cols-2"
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  <CompactFact
                    label="Выручка"
                    value={formatMoney(row.revenue)}
                    note={`${formatNumber(row.sales_qty)} продаж`}
                  />
                  <CompactFact
                    label="К выплате"
                    value={formatMoney(row.for_pay)}
                    note={`маржа ${formatPercent(row.margin_percent)}`}
                  />
                  <CompactFact
                    label="Средний чек"
                    value={formatMoney(calc.avgSaleValue)}
                    note={`выкуп ${formatPercent(row.buyout_percent)}`}
                  />
                  <CompactFact
                    label="Прибыль после логистики"
                    value={formatMoney(calc.marginAfterLogistics)}
                    note="без дубля возвратной логистики"
                  />
                </div>
                <div className="space-y-3 rounded-md border bg-background p-4">
                  <CostLine
                    label="Доставка"
                    value={row.logistics_cost}
                    total={calc.totalLogistics}
                  />
                  <CostLine
                    label="Возвраты"
                    value={row.return_logistics_cost}
                    total={calc.totalLogistics}
                  />
                  <CostLine
                    label="Хранение"
                    value={row.storage_cost}
                    total={calc.totalLogistics}
                  />
                  <CostLine
                    label="Приёмка"
                    value={row.acceptance_cost}
                    total={calc.totalLogistics}
                  />
                </div>
              </TabsContent>
              <TabsContent
                value="stock"
                className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
              >
                <CompactFact
                  label="На WB"
                  value={formatNumber(row.stock_units)}
                  note="шт"
                />
                <CompactFact
                  label="К клиенту"
                  value={formatNumber(row.in_way_to_client)}
                  note="в пути"
                />
                <CompactFact
                  label="Возвраты"
                  value={formatNumber(row.in_way_from_client)}
                  note="в пути"
                />
                <CompactFact
                  label="Цель 14 дн."
                  value={formatNumber(calc.targetStock)}
                  note={`${formatNumber(calc.avgDailySales)} / день`}
                />
              </TabsContent>
              <TabsContent value="sku" className="mt-4">
                <ProductMiniTable
                  products={sortProductRows(products).slice(0, 40)}
                />
              </TabsContent>
              <TabsContent
                value="acceptance"
                className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
              >
                <CompactFact
                  label="Статус"
                  value={acceptanceLabel(row.acceptance_status)}
                  note={`k=${row.acceptance_coefficient ?? "—"}`}
                />
                <CompactFact
                  label="Разгрузка"
                  value={row.allow_unload === false ? "нет" : "да"}
                  note={`${row.box_type_ids.length || 0} типов коробов`}
                />
                <CompactFact
                  label="База доставки"
                  value={formatMoney(row.delivery_base)}
                  note="за короб"
                />
                <CompactFact
                  label="Литр доставки"
                  value={formatMoney(row.delivery_liter)}
                  note="доп. литр"
                />
              </TabsContent>
              <TabsContent value="plan" className="mt-4 space-y-4">
                <Alert className={severitySoftClass(row.risk_level)}>
                  <Gauge className="h-4 w-4" />
                  <AlertTitle>{calc.priority}</AlertTitle>
                  <AlertDescription>
                    {row.recommendation ||
                      "Склад держит нормальный запас и приемлемую стоимость логистики."}
                  </AlertDescription>
                </Alert>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <CompactFact
                    label="Открытые поставки"
                    value={formatNumber(row.open_supply_count)}
                    note={`${formatNumber(row.supply_count)} всего`}
                  />
                  <CompactFact
                    label="Нужно докинуть"
                    value={`+${formatNumber(calc.replenishmentQty)}`}
                    note={`${FAST_REPLENISHMENT_DAYS} дн.`}
                  />
                  <CompactFact
                    label="Спрос региона"
                    value={`${formatNumber(row.region_sales_qty)} шт`}
                    note={formatMoney(row.region_sales_amount)}
                  />
                  <CompactFact
                    label="Доля региона"
                    value={formatPercent(row.region_sales_share_percent)}
                    note="в продажах"
                  />
                </div>
                <SupplyWorkspace rows={relatedSupplies.slice(0, 12)} />
              </TabsContent>
            </Tabs>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function LogisticsDetailsWorkspace({
  paidStorage,
  acceptance,
  transit,
  sellerWarehouses,
  sources,
  capabilities,
  onExport,
  exportingDataset,
}: {
  paidStorage: PaidStorageDetailRow[];
  acceptance: AcceptanceDetailRow[];
  transit: TransitTariffRow[];
  sellerWarehouses: SellerWarehouseRow[];
  sources: DataSourceRow[];
  capabilities: CapabilityRow[];
  onExport: (dataset: LogisticsExportDataset) => void;
  exportingDataset: LogisticsExportDataset | null;
}) {
  const storageTotal = paidStorage.reduce((sum, row) => sum + row.amount, 0);
  const acceptanceTotal = acceptance.reduce((sum, row) => sum + row.amount, 0);
  const sellerStockTotal = sellerWarehouses.reduce(
    (sum, row) => sum + row.stock_units,
    0,
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <ExecutiveMetric
          title="Хранение по SKU"
          value={formatMoney(storageTotal)}
          detail={`${formatNumber(paidStorage.length)} строк детализации`}
          icon={Layers3}
          tone="amber"
        />
        <ExecutiveMetric
          title="Приёмка по операциям"
          value={formatMoney(acceptanceTotal)}
          detail={`${formatNumber(acceptance.length)} операций`}
          icon={PackageCheck}
          tone="blue"
        />
        <ExecutiveMetric
          title="Транзитные маршруты"
          value={formatNumber(transit.length)}
          detail="тарифы и сроки поставки"
          icon={RouteIcon}
          tone="teal"
        />
        <ExecutiveMetric
          title="Остаток FBS/DBW"
          value={formatNumber(sellerStockTotal)}
          detail={`${formatNumber(sellerWarehouses.length)} складов продавца`}
          icon={Warehouse}
          tone="red"
        />
      </div>

      <Tabs defaultValue="storage" className="w-full">
        <TabsList className="h-auto flex-wrap">
          <TabsTrigger value="storage" className="text-xs">
            Хранение
          </TabsTrigger>
          <TabsTrigger value="acceptance" className="text-xs">
            Приёмка
          </TabsTrigger>
          <TabsTrigger value="transit" className="text-xs">
            Транзит
          </TabsTrigger>
          <TabsTrigger value="seller" className="text-xs">
            FBS/DBW
          </TabsTrigger>
          <TabsTrigger value="sources" className="text-xs">
            Источники
          </TabsTrigger>
        </TabsList>
        <TabsContent value="storage" className="mt-3">
          <PaidStorageDetailsTable
            rows={paidStorage}
            onExport={() => onExport("paid_storage")}
            exporting={exportingDataset === "paid_storage"}
          />
        </TabsContent>
        <TabsContent value="acceptance" className="mt-3">
          <AcceptanceDetailsTable
            rows={acceptance}
            onExport={() => onExport("acceptance")}
            exporting={exportingDataset === "acceptance"}
          />
        </TabsContent>
        <TabsContent value="transit" className="mt-3">
          <TransitTariffTable
            rows={transit}
            onExport={() => onExport("transit")}
            exporting={exportingDataset === "transit"}
          />
        </TabsContent>
        <TabsContent value="seller" className="mt-3">
          <SellerWarehouseTable
            rows={sellerWarehouses}
            onExport={() => onExport("seller_warehouses")}
            exporting={exportingDataset === "seller_warehouses"}
          />
        </TabsContent>
        <TabsContent value="sources" className="mt-3">
          <SourceCoveragePanel sources={sources} capabilities={capabilities} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function PaidStorageDetailsTable({
  rows,
  onExport,
  exporting,
}: {
  rows: PaidStorageDetailRow[];
  onExport: () => void;
  exporting: boolean;
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "amount", desc: true },
  ]);
  const columns = useMemo<ColumnDef<PaidStorageDetailRow>[]>(
    () => [
      {
        id: "product",
        accessorFn: (row) => detailProductLabel(row),
        header: ({ column }) => (
          <SortableHeader column={column} label="Товар" />
        ),
        cell: ({ row }) => <DetailProductCell row={row.original} />,
      },
      {
        id: "warehouse",
        accessorFn: (row) => row.warehouse_name || "",
        header: ({ column }) => (
          <SortableHeader column={column} label="Склад" />
        ),
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="truncate font-medium">
              {row.original.warehouse_name || "—"}
            </div>
            <div className="text-xs text-muted-foreground">
              {formatDate(row.original.report_date)}
            </div>
          </div>
        ),
      },
      {
        id: "quantity",
        accessorFn: (row) => row.quantity,
        header: ({ column }) => (
          <SortableHeader column={column} label="Кол-во" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right font-medium">
            {formatNumber(row.original.quantity)}
          </div>
        ),
      },
      {
        id: "amount",
        accessorFn: (row) => row.amount,
        header: ({ column }) => (
          <SortableHeader column={column} label="Сумма" align="right" />
        ),
        cell: ({ row }) => (
          <NumberCell
            value={formatMoney(row.original.amount)}
            note={formatPercent(row.original.share_percent)}
            strong
          />
        ),
      },
      {
        id: "amount_per_unit",
        accessorFn: (row) => row.amount_per_unit || 0,
        header: ({ column }) => (
          <SortableHeader column={column} label="За шт." align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right font-medium">
            {formatMoney(row.original.amount_per_unit)}
          </div>
        ),
      },
    ],
    [],
  );
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  return (
    <DetailsTableShell
      title="Детальный отчёт платного хранения"
      description="Товары, склады, даты и сумма хранения из отдельного WB report."
      emptyTitle="Детализация хранения ещё не загружена"
      emptyText="Запустите sync logistics: модуль создаст отчёт /api/v1/paid_storage и скачает детализацию."
      rowsLength={rows.length}
      onExport={onExport}
      exporting={exporting}
    >
      <DesktopSortableTable table={table} />
    </DetailsTableShell>
  );
}

function AcceptanceDetailsTable({
  rows,
  onExport,
  exporting,
}: {
  rows: AcceptanceDetailRow[];
  onExport: () => void;
  exporting: boolean;
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "amount", desc: true },
  ]);
  const columns = useMemo<ColumnDef<AcceptanceDetailRow>[]>(
    () => [
      {
        id: "product",
        accessorFn: (row) => detailProductLabel(row),
        header: ({ column }) => (
          <SortableHeader column={column} label="Товар" />
        ),
        cell: ({ row }) => <DetailProductCell row={row.original} />,
      },
      {
        id: "operation",
        accessorFn: (row) => row.operation_name || "",
        header: ({ column }) => (
          <SortableHeader column={column} label="Операция" />
        ),
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="truncate font-medium">
              {row.original.operation_name || "Приёмка"}
            </div>
            <div className="text-xs text-muted-foreground">
              {formatDate(row.original.operation_date)}
            </div>
          </div>
        ),
      },
      {
        id: "warehouse",
        accessorFn: (row) => row.warehouse_name || "",
        header: ({ column }) => (
          <SortableHeader column={column} label="Склад" />
        ),
        cell: ({ row }) => row.original.warehouse_name || "—",
      },
      {
        id: "quantity",
        accessorFn: (row) => row.quantity,
        header: ({ column }) => (
          <SortableHeader column={column} label="Кол-во" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right font-medium">
            {formatNumber(row.original.quantity)}
          </div>
        ),
      },
      {
        id: "amount",
        accessorFn: (row) => row.amount,
        header: ({ column }) => (
          <SortableHeader column={column} label="Сумма" align="right" />
        ),
        cell: ({ row }) => (
          <NumberCell
            value={formatMoney(row.original.amount)}
            note={formatPercent(row.original.share_percent)}
            strong
          />
        ),
      },
    ],
    [],
  );
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  return (
    <DetailsTableShell
      title="Детальный отчёт расходов приёмки"
      description="Сверка по операциям, складам и товарам из /api/v1/acceptance_report."
      emptyTitle="Детализация приёмки ещё не загружена"
      emptyText="Запустите sync logistics: модуль скачает acceptance report и покажет операции вместо одной общей суммы из finance detailed."
      rowsLength={rows.length}
      onExport={onExport}
      exporting={exporting}
    >
      <DesktopSortableTable table={table} />
    </DetailsTableShell>
  );
}

function TransitTariffTable({
  rows,
  onExport,
  exporting,
}: {
  rows: TransitTariffRow[];
  onExport: () => void;
  exporting: boolean;
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "amount", desc: false },
  ]);
  const columns = useMemo<ColumnDef<TransitTariffRow>[]>(
    () => [
      {
        id: "route",
        accessorFn: (row) => row.route_label || "",
        header: ({ column }) => (
          <SortableHeader column={column} label="Маршрут" />
        ),
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="truncate font-medium">
              {row.original.route_label || "Маршрут без названия"}
            </div>
            <div className="truncate text-xs text-muted-foreground">
              {row.original.source_warehouse_name || "откуда"} →{" "}
              {row.original.transit_warehouse_name || "транзит"} →{" "}
              {row.original.destination_warehouse_name || "куда"}
            </div>
          </div>
        ),
      },
      {
        id: "amount",
        accessorFn: (row) => row.amount || 0,
        header: ({ column }) => (
          <SortableHeader column={column} label="Тариф" align="right" />
        ),
        cell: ({ row }) => (
          <NumberCell value={formatMoney(row.original.amount)} strong />
        ),
      },
      {
        id: "delivery_base",
        accessorFn: (row) => row.delivery_base || 0,
        header: ({ column }) => (
          <SortableHeader column={column} label="База" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right">
            {formatMoney(row.original.delivery_base)}
          </div>
        ),
      },
      {
        id: "delivery_liter",
        accessorFn: (row) => row.delivery_liter || 0,
        header: ({ column }) => (
          <SortableHeader column={column} label="Литр" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right">
            {formatMoney(row.original.delivery_liter)}
          </div>
        ),
      },
      {
        id: "transit_time_days",
        accessorFn: (row) => row.transit_time_days || 0,
        header: ({ column }) => (
          <SortableHeader column={column} label="Срок" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right">
            {row.original.transit_time_days == null
              ? "—"
              : `${formatNumber(row.original.transit_time_days)} дн.`}
          </div>
        ),
      },
      {
        id: "coefficient",
        accessorFn: (row) => row.coefficient || "",
        header: ({ column }) => (
          <SortableHeader column={column} label="Коэф." align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right">{row.original.coefficient || "—"}</div>
        ),
      },
    ],
    [],
  );
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  return (
    <DetailsTableShell
      title="Транзитные направления и тарифы"
      description="Маршруты supplies-api для выбора поставки через транзитный склад."
      emptyTitle="Транзитные тарифы ещё не загружены"
      emptyText="Нужен supplies token и sync logistics: модуль запросит /api/v1/transit-tariffs."
      rowsLength={rows.length}
      onExport={onExport}
      exporting={exporting}
    >
      <DesktopSortableTable table={table} />
    </DetailsTableShell>
  );
}

function SellerWarehouseTable({
  rows,
  onExport,
  exporting,
}: {
  rows: SellerWarehouseRow[];
  onExport: () => void;
  exporting: boolean;
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "stock_units", desc: true },
  ]);
  const columns = useMemo<ColumnDef<SellerWarehouseRow>[]>(
    () => [
      {
        id: "name",
        accessorFn: (row) => row.name || "",
        header: ({ column }) => (
          <SortableHeader column={column} label="Склад продавца" />
        ),
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="truncate font-medium">
              {row.original.name || `Склад ${row.original.warehouse_id}`}
            </div>
            <div className="truncate text-xs text-muted-foreground">
              ID {row.original.warehouse_id}
              {row.original.office_id
                ? ` · офис ${row.original.office_id}`
                : ""}
            </div>
          </div>
        ),
      },
      {
        id: "delivery_type",
        accessorFn: (row) =>
          deliveryTypeLabel(row.delivery_type_label || row.delivery_type),
        header: ({ column }) => (
          <SortableHeader column={column} label="Модель" />
        ),
        cell: ({ row }) => (
          <Badge variant="outline">
            {deliveryTypeLabel(
              row.original.delivery_type_label || row.original.delivery_type,
            )}
          </Badge>
        ),
      },
      {
        id: "stock_units",
        accessorFn: (row) => row.stock_units,
        header: ({ column }) => (
          <SortableHeader column={column} label="Остаток" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right font-semibold">
            {formatNumber(row.original.stock_units)}
          </div>
        ),
      },
      {
        id: "stock_rows",
        accessorFn: (row) => row.stock_rows,
        header: ({ column }) => (
          <SortableHeader column={column} label="Размеров" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right">
            {formatNumber(row.original.stock_rows)}
          </div>
        ),
      },
      {
        id: "is_active",
        accessorFn: (row) => (row.is_active === false ? 0 : 1),
        header: ({ column }) => (
          <SortableHeader column={column} label="Статус" />
        ),
        cell: ({ row }) => (
          <StatusBadge
            status={row.original.is_active === false ? "empty" : "ok"}
          />
        ),
      },
      {
        id: "latest_stock_at",
        accessorFn: (row) => row.latest_stock_at || "",
        header: ({ column }) => (
          <SortableHeader column={column} label="Обновлено" />
        ),
        cell: ({ row }) => formatDateTime(row.original.latest_stock_at),
      },
    ],
    [],
  );
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  return (
    <DetailsTableShell
      title="Склады продавца FBS/DBW и остатки"
      description="Marketplace API: список складов и остатки по chrtId для склада продавца."
      emptyTitle="Склады продавца ещё не загружены"
      emptyText="Нужен marketplace token и sync logistics. Для остатков используются chrtId из карточек товаров."
      rowsLength={rows.length}
      onExport={onExport}
      exporting={exporting}
    >
      <DesktopSortableTable table={table} />
    </DetailsTableShell>
  );
}

function SourceCoveragePanel({
  sources,
  capabilities,
}: {
  sources: DataSourceRow[];
  capabilities: CapabilityRow[];
}) {
  const okCount = sources.filter((source) => source.status === "ok").length;
  const pct = sources.length ? (okCount / sources.length) * 100 : 0;
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
      <Card className="rounded-md">
        <CardHeader className="border-b p-4">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-base">Покрытие данных</CardTitle>
            <Badge variant="outline">{formatPercent(pct, 0)}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-4">
          <Progress value={pct} className="h-2" />
          <div className="grid gap-2 md:grid-cols-2">
            {sources.map((source) => (
              <div
                key={source.key}
                className="flex items-center justify-between gap-3 rounded-md border px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">
                    {source.label}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {formatNumber(source.rows)} строк
                    {source.latest_at
                      ? ` · ${formatDateTime(source.latest_at)}`
                      : ""}
                  </div>
                  {source.note && (
                    <div className="mt-0.5 line-clamp-2 text-xs text-amber-700">
                      {source.note}
                    </div>
                  )}
                </div>
                <StatusBadge status={source.status} />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
      <Card className="rounded-md">
        <CardHeader className="border-b p-4">
          <CardTitle className="text-base">Возможности WB API</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 p-3">
          {capabilities.map((item) => (
            <div key={item.key} className="rounded-md border px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">
                    {item.label}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {tokenCategoryLabel(item.token_category)}
                  </div>
                </div>
                <StatusBadge status={item.status} />
              </div>
              <div className="mt-2 truncate font-mono text-[11px] text-muted-foreground">
                {item.endpoint}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function DetailsTableShell({
  title,
  description,
  emptyTitle,
  emptyText,
  rowsLength,
  onExport,
  exporting,
  children,
}: {
  title: string;
  description: string;
  emptyTitle: string;
  emptyText: string;
  rowsLength: number;
  onExport: () => void;
  exporting: boolean;
  children: ReactNode;
}) {
  if (!rowsLength) {
    return (
      <Alert className="rounded-md">
        <Database className="h-4 w-4" />
        <AlertTitle>{emptyTitle}</AlertTitle>
        <AlertDescription>{emptyText}</AlertDescription>
      </Alert>
    );
  }
  return (
    <Card className="rounded-md">
      <CardHeader className="border-b p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base">{title}</CardTitle>
            <div className="mt-1 text-xs text-muted-foreground">
              {description}
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="gap-2"
            onClick={onExport}
            disabled={exporting}
          >
            <Download className="h-4 w-4" />
            CSV
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">{children}</CardContent>
    </Card>
  );
}

function DesktopSortableTable<TData>({
  table,
}: {
  table: ReactTableInstance<TData>;
}) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id}>
                  {header.isPlaceholder
                    ? null
                    : flexRender(
                        header.column.columnDef.header,
                        header.getContext(),
                      )}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => (
            <TableRow key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function DetailProductCell({
  row,
}: {
  row: PaidStorageDetailRow | AcceptanceDetailRow;
}) {
  return (
    <div className="min-w-0">
      <div className="truncate font-medium">{detailProductLabel(row)}</div>
      <div className="truncate text-xs text-muted-foreground">
        WB {row.nm_id ?? "—"}
        {row.barcode ? ` · ${row.barcode}` : ""}
      </div>
    </div>
  );
}

function SupplyWorkspace({ rows }: { rows: SupplyRow[] }) {
  const totals = rows.reduce(
    (acc, row) => ({
      planned: acc.planned + row.planned_qty,
      accepted: acc.accepted + row.accepted_qty,
      gap: acc.gap + row.gap_qty,
      open:
        acc.open + (row.status_id && ![5, 6].includes(row.status_id) ? 1 : 0),
    }),
    { planned: 0, accepted: 0, gap: 0, open: 0 },
  );

  if (!rows.length) {
    return (
      <Alert className="rounded-md">
        <Factory className="h-4 w-4" />
        <AlertTitle>Поставки не найдены</AlertTitle>
        <AlertDescription>
          Список появится после загрузки FBO-поставок и товаров в поставках.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      <Card className="rounded-md">
        <CardContent className="grid gap-0 p-0 sm:grid-cols-4 sm:divide-x">
          <DetailStat
            label="Поставок"
            value={formatNumber(rows.length)}
            icon={Factory}
          />
          <DetailStat
            label="В работе"
            value={formatNumber(totals.open)}
            icon={Activity}
          />
          <DetailStat
            label="План"
            value={formatNumber(totals.planned)}
            icon={Boxes}
          />
          <DetailStat
            label="Разница"
            value={formatNumber(totals.gap)}
            icon={AlertTriangle}
          />
        </CardContent>
      </Card>
      <Card className="rounded-md">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Поставка</TableHead>
                  <TableHead>Склад</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead className="text-right">План</TableHead>
                  <TableHead className="text-right">Принято</TableHead>
                  <TableHead className="text-right">Разница</TableHead>
                  <TableHead>Дата</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.supply_id}>
                    <TableCell className="font-medium">
                      #{row.supply_id}
                    </TableCell>
                    <TableCell>
                      <div>
                        {row.actual_warehouse_name || row.warehouse_name || "—"}
                      </div>
                      {row.box_type_id && (
                        <div className="text-xs text-muted-foreground">
                          тип короба {row.box_type_id}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {supplyStatusLabel(row.status_label)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {formatNumber(row.planned_qty)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatNumber(row.accepted_qty)}
                    </TableCell>
                    <TableCell className="text-right">
                      <span
                        className={cn(
                          row.gap_qty > 0 && "font-medium text-destructive",
                        )}
                      >
                        {formatNumber(row.gap_qty)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div>{formatDateTime(row.supply_date)}</div>
                      {row.fact_date && (
                        <div className="text-xs text-muted-foreground">
                          факт {formatDateTime(row.fact_date)}
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ProductMiniTable({
  products,
  compact = false,
}: {
  products: ProductRow[];
  compact?: boolean;
}) {
  if (!products.length) {
    return (
      <div className="rounded-md border bg-muted/20 px-3 py-4 text-sm text-muted-foreground">
        Артикулы не найдены
      </div>
    );
  }

  if (compact) {
    return (
      <div className="overflow-hidden rounded-md border">
        <div className="divide-y">
          {products.map((product) => (
            <div key={product.id} className="grid gap-2 px-3 py-3 text-sm">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate font-medium">
                    {productLabel(product)}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    WB {product.nm_id ?? "—"} · {product.brand || "бренд —"}
                  </div>
                </div>
                <RiskBadge level={product.risk_level} />
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <MetricInline
                  label="Остаток"
                  value={formatNumber(product.stock_units)}
                />
                <MetricInline
                  label="30 дн."
                  value={`+${formatNumber(product.recommended_supply_30)}`}
                />
                <MetricInline
                  label="Эффект"
                  value={formatMoney(product.expected_net_effect)}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-[220px]">Артикул</TableHead>
              <TableHead>Риск</TableHead>
              <TableHead className="text-right">Остаток</TableHead>
              <TableHead className="text-right">Продажи</TableHead>
              <TableHead className="text-right">План 30 дн.</TableHead>
              <TableHead className="text-right">Чистый эффект</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {products.map((product) => (
              <TableRow key={product.id}>
                <TableCell>
                  <div className="min-w-0">
                    <div className="truncate font-medium">
                      {productLabel(product)}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      WB {product.nm_id ?? "—"} · {product.brand || "бренд —"}
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <RiskBadge level={product.risk_level} />
                </TableCell>
                <TableCell className="text-right">
                  {formatNumber(product.stock_units)}
                </TableCell>
                <TableCell className="text-right">
                  <NumberCell
                    value={formatNumber(product.sales_qty)}
                    note={`${formatNumber(product.avg_daily_sales)} / день`}
                  />
                </TableCell>
                <TableCell className="text-right font-medium">
                  +{formatNumber(product.recommended_supply_30)}
                </TableCell>
                <TableCell className="text-right">
                  <NumberCell
                    value={formatMoney(product.expected_net_effect)}
                    note={formatMoney(product.potential_revenue)}
                    strong
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function DetailStat({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
}) {
  return (
    <div className="min-w-0 p-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        <span className="truncate">{label}</span>
      </div>
      <div className="mt-1 truncate text-lg font-semibold">{value}</div>
    </div>
  );
}

function CompactFact({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="min-w-0 rounded-md border bg-muted/20 p-3">
      <div className="truncate text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 truncate text-sm font-semibold">{value}</div>
      {note && (
        <div className="mt-1 truncate text-xs text-muted-foreground">
          {note}
        </div>
      )}
    </div>
  );
}

function NumberCell({
  value,
  note,
  strong = false,
}: {
  value: string;
  note?: string;
  strong?: boolean;
}) {
  return (
    <div className="text-right">
      <div className={cn(strong ? "font-semibold" : "font-medium")}>
        {value}
      </div>
      {note && <div className="text-xs text-muted-foreground">{note}</div>}
    </div>
  );
}

function MetricInline({
  label,
  value,
  align = "right",
}: {
  label: string;
  value: string;
  align?: "left" | "right";
}) {
  return (
    <span
      className={cn("min-w-0 text-xs", align === "right" && "lg:text-right")}
    >
      <span className="block text-muted-foreground">{label}</span>
      <span className="block truncate font-semibold">{value}</span>
    </span>
  );
}

function FormulaLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/20 px-3 py-2">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-xs">{value}</div>
    </div>
  );
}

function CostLine({
  label,
  value,
  total,
}: {
  label: string;
  value: number;
  total: number;
}) {
  const pct = total ? Math.min((Math.max(value, 0) / total) * 100, 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{formatMoney(value)}</span>
      </div>
      <Progress value={pct} className="h-1.5" />
    </div>
  );
}

function SortableHeader<TData>({
  column,
  label,
  align = "left",
}: {
  column: Column<TData, unknown>;
  label: string;
  align?: "left" | "right";
}) {
  const sorted = column.getIsSorted();
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={cn(
        "-mx-2 h-8 gap-1 px-2 text-xs font-medium",
        align === "right" && "ml-auto -mr-2",
      )}
      onClick={column.getToggleSortingHandler()}
      disabled={!column.getCanSort()}
    >
      <span>{label}</span>
      {sorted === "asc" ? (
        <ArrowDown className="h-3.5 w-3.5 rotate-180" />
      ) : sorted === "desc" ? (
        <ArrowDown className="h-3.5 w-3.5" />
      ) : (
        <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
      )}
    </Button>
  );
}

function relatedProductsForTask(
  products: ProductRow[],
  task: LogisticsTaskRow,
) {
  const related = products.filter((product) => {
    if (task.warehouse_name)
      return product.warehouse_name === task.warehouse_name;
    if (task.region_name) return product.region_name === task.region_name;
    return true;
  });
  return sortProductRows(related).slice(0, 40);
}

function sortProductRows(products: ProductRow[]) {
  return [...products].sort((a, b) => {
    const riskDelta = riskWeight(a.risk_level) - riskWeight(b.risk_level);
    if (riskDelta) return riskDelta;
    const netDelta = b.expected_net_effect - a.expected_net_effect;
    if (netDelta) return netDelta;
    return b.recommended_supply_30 - a.recommended_supply_30;
  });
}

function calculateWarehouse(
  row: WarehouseRow,
  periodDays: number,
): WarehouseCalculated {
  const totalLogistics =
    row.logistics_cost +
    row.return_logistics_cost +
    row.storage_cost +
    row.acceptance_cost;
  const avgDailySales = periodDays ? row.sales_qty / periodDays : 0;
  const targetStock = Math.ceil(avgDailySales * FAST_REPLENISHMENT_DAYS);
  const replenishmentQty = Math.max(targetStock - row.stock_units, 0);
  const stockCoveragePercent =
    row.turnover_days == null
      ? 0
      : Math.min(
          Math.max((row.turnover_days / FAST_REPLENISHMENT_DAYS) * 100, 0),
          100,
        );

  return {
    totalLogistics,
    costPerOrder: divide(totalLogistics, row.orders_qty),
    costPerSale: divide(totalLogistics, row.sales_qty),
    avgDailySales,
    avgSaleValue: divide(row.revenue, row.sales_qty),
    targetStock,
    replenishmentQty,
    stockCoveragePercent,
    marginAfterLogistics: row.for_pay - totalLogistics,
    priority: priorityLabel(row),
  };
}

function divide(numerator: number, denominator: number) {
  if (!denominator) return null;
  return numerator / denominator;
}

function getInclusiveDays(from?: string, to?: string) {
  if (!from || !to) return 30;
  const start = new Date(`${from}T00:00:00Z`).getTime();
  const end = new Date(`${to}T00:00:00Z`).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return 30;
  return Math.max(Math.round((end - start) / 86_400_000) + 1, 1);
}

function disabledWarehouseKey(accountId: number) {
  return `wb.logistics.disabled_warehouses.${accountId}`;
}

function productLabel(product: ProductRow) {
  return (
    product.vendor_code ||
    product.title ||
    product.barcode ||
    (product.nm_id ? String(product.nm_id) : "артикул")
  );
}

function detailProductLabel(row: PaidStorageDetailRow | AcceptanceDetailRow) {
  return row.vendor_code || row.title || row.barcode || row.brand || "товар";
}

function compactProduct(name: string) {
  if (!name) return "—";
  return name.length > 15 ? `${name.slice(0, 14)}…` : name;
}

function priorityLabel(row: WarehouseRow) {
  if (row.risk_level === "danger") return "Срочно";
  if (row.risk_level === "warning") return "Сегодня";
  if (row.risk_level === "watch") return "Контроль";
  return "Планово";
}

function riskWeight(level: string) {
  if (level === "danger") return 0;
  if (level === "warning") return 1;
  if (level === "watch") return 2;
  return 3;
}

function acceptanceLabel(status: string) {
  return (
    {
      available: "доступно",
      expensive: "дорого",
      closed: "закрыто",
      unknown: "нет данных",
    }[status] || statusLabel(status)
  );
}

function confidenceLabel(value: string) {
  if (value === "high") return "высокая точность";
  if (value === "low") return "мало данных";
  return "средняя точность";
}

function supplyStatusLabel(value: string) {
  const normalized = value.toLowerCase();
  if (normalized.includes("draft")) return "Черновик";
  if (normalized.includes("active")) return "В работе";
  if (normalized.includes("done") || normalized.includes("closed"))
    return "Закрыта";
  if (normalized.includes("cancel")) return "Отменена";
  return value;
}

function deliveryTypeLabel(value?: string | null) {
  if (!value) return "—";
  const normalized = value.toLowerCase();
  if (normalized.includes("fbs")) return "FBS";
  if (normalized.includes("dbw")) return "DBW";
  if (normalized.includes("seller")) return "Склад продавца";
  return value;
}

function tokenCategoryLabel(value: string) {
  return (
    {
      analytics: "Аналитика",
      supplies: "Поставки",
      marketplace: "Маркетплейс",
      finance: "Финансы",
      content: "Контент",
      prices: "Цены",
      statistics: "Статистика",
    }[value] || value
  );
}

function statusLabel(status: string) {
  return (
    {
      ok: "ОК",
      active: "Активно",
      available: "Доступно",
      planned: "В плане",
      expensive: "Дорого",
      stale: "Устарело",
      closed: "Закрыто",
      empty: "Нет данных",
      missing: "Нет данных",
      unknown: "Неизвестно",
      warning: "Риск",
      danger: "Критично",
      watch: "Наблюдать",
    }[status] || status
  );
}

function RiskBadge({ level }: { level: string }) {
  return <Badge className={riskClass(level)}>{statusLabel(level)}</Badge>;
}

function StatusBadge({ status }: { status: string }) {
  const className =
    {
      ok: "border-emerald-200 bg-emerald-50 text-emerald-700",
      active: "border-emerald-200 bg-emerald-50 text-emerald-700",
      available: "border-emerald-200 bg-emerald-50 text-emerald-700",
      planned: "border-amber-200 bg-amber-50 text-amber-700",
      expensive: "border-amber-200 bg-amber-50 text-amber-700",
      stale: "border-amber-200 bg-amber-50 text-amber-700",
      closed: "border-red-200 bg-red-50 text-red-700",
      empty: "border-slate-200 bg-slate-50 text-slate-600",
      missing: "border-slate-200 bg-slate-50 text-slate-600",
      unknown: "border-slate-200 bg-slate-50 text-slate-600",
    }[status] || "border-slate-200 bg-slate-50 text-slate-600";
  return (
    <Badge variant="outline" className={className}>
      {statusLabel(status)}
    </Badge>
  );
}

function WarehouseModeBadge({ mode }: { mode: string }) {
  const meta = {
    active: ["Активен", "border-emerald-200 bg-emerald-50 text-emerald-700"],
    pause_tasks: ["Пауза задач", "border-red-200 bg-red-50 text-red-700"],
    pause_replenishment: [
      "Пауза поставок",
      "border-amber-200 bg-amber-50 text-amber-700",
    ],
    review_economics: [
      "Проверить экономику",
      "border-orange-200 bg-orange-50 text-orange-700",
    ],
  }[mode] || [statusLabel(mode), "border-slate-200 bg-slate-50 text-slate-600"];
  return (
    <Badge variant="outline" className={meta[1]}>
      {meta[0]}
    </Badge>
  );
}

function riskClass(level: string) {
  if (level === "danger") return "bg-red-600 text-white hover:bg-red-600";
  if (level === "warning")
    return "bg-orange-500 text-white hover:bg-orange-500";
  if (level === "watch")
    return "bg-amber-100 text-amber-800 hover:bg-amber-100";
  return "bg-emerald-100 text-emerald-800 hover:bg-emerald-100";
}

function severitySoftClass(level: string) {
  if (level === "danger") return "border-red-200 bg-red-50 text-red-900";
  if (level === "warning")
    return "border-orange-200 bg-orange-50 text-orange-900";
  if (level === "ok")
    return "border-emerald-200 bg-emerald-50 text-emerald-900";
  return "border-amber-200 bg-amber-50 text-amber-900";
}
