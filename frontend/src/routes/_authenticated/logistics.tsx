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
  Filter,
  Gauge,
  Info,
  Layers3,
  ListChecks,
  MapPin,
  PackageCheck,
  PackagePlus,
  PackageSearch,
  PanelRightOpen,
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
import { api } from "@/lib/api";
import { useAccounts } from "@/lib/account-context";
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
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

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
    staleTime: 60_000,
    retry: false,
  });

  const rawData = query.data;
  const data = isLogisticsOverview(rawData) ? rawData : null;
  const hasUnexpectedPayload = Boolean(rawData && !data);
  const kpis = data?.kpis;
  const warehouses = useMemo(() => data?.warehouses ?? [], [data?.warehouses]);
  const rawTasks = useMemo(() => data?.tasks ?? [], [data?.tasks]);
  const rawProducts = useMemo(() => data?.products ?? [], [data?.products]);
  const rawRegionalShipments = useMemo(
    () => data?.regional_shipments ?? [],
    [data?.regional_shipments],
  );
  const warehouseControls = useMemo(
    () => data?.warehouse_controls ?? [],
    [data?.warehouse_controls],
  );
  const paidStorageDetails = useMemo(
    () => data?.paid_storage_details ?? [],
    [data?.paid_storage_details],
  );
  const acceptanceDetails = useMemo(
    () => data?.acceptance_details ?? [],
    [data?.acceptance_details],
  );
  const transitTariffs = useMemo(
    () => data?.transit_tariffs ?? [],
    [data?.transit_tariffs],
  );
  const sellerWarehouses = useMemo(
    () => data?.seller_warehouses ?? [],
    [data?.seller_warehouses],
  );
  const tasks = useMemo(
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
  const periodDays = useMemo(
    () => getInclusiveDays(data?.period?.date_from, data?.period?.date_to),
    [data?.period?.date_from, data?.period?.date_to],
  );
  const selectedWarehouse = useMemo(
    () =>
      warehouses.find((row) => row.warehouse_name === selectedWarehouseName) ??
      warehouses[0] ??
      null,
    [selectedWarehouseName, warehouses],
  );
  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) ?? tasks[0] ?? null,
    [selectedTaskId, tasks],
  );
  const chartRows = useMemo(
    () =>
      warehouses.slice(0, 12).map((row) => ({
        name: compactWarehouse(row.warehouse_name),
        revenue: Math.round(row.revenue || 0),
        costs: Math.round(
          (row.logistics_cost || 0) +
            (row.return_logistics_cost || 0) +
            (row.storage_cost || 0) +
            (row.acceptance_cost || 0),
        ),
        risk: row.risk_level,
      })),
    [warehouses],
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
        title="Логистика"
        description="Склады, поставки, тарифы, расходы и потерянные заказы WB в одном рабочем контуре."
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
          <div className="flex flex-col gap-3 rounded-lg border bg-background p-3 md:flex-row md:items-center md:justify-between">
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Склад или регион"
                className="h-9 max-w-lg"
              />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline" className="gap-1">
                <Clock className="h-3.5 w-3.5" />
                {formatDate(range.from)} - {formatDate(range.to)}
              </Badge>
              {data?.generated_at && (
                <Badge variant="outline" className="gap-1">
                  <Database className="h-3.5 w-3.5" />
                  {formatDateTime(data.generated_at)}
                </Badge>
              )}
            </div>
          </div>

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
                Сервер вернул данные без обязательных полей периода или
                разделов. Обновите страницу после синхронизации или проверьте
                маршрут `/portal/logistics/overview`.
              </AlertDescription>
            </Alert>
          )}

          {data && (
            <>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-8">
                <MetricCard
                  label="Выручка"
                  value={formatMoney(kpis?.revenue)}
                  icon={RouteIcon}
                  tone="blue"
                  note={`${formatNumber(kpis?.orders_qty)} заказов`}
                />
                <MetricCard
                  label="Логистика"
                  value={formatMoney(
                    (kpis?.logistics_cost || 0) +
                      (kpis?.return_logistics_cost || 0) +
                      (kpis?.storage_cost || 0) +
                      (kpis?.acceptance_cost || 0),
                  )}
                  icon={Truck}
                  tone="orange"
                  note={formatPercent(kpis?.logistics_share_percent)}
                />
                <MetricCard
                  label="Хранение SKU"
                  value={formatMoney(kpis?.paid_storage_detail_cost)}
                  icon={Layers3}
                  tone="violet"
                  note={`${formatNumber(kpis?.paid_storage_detail_rows)} строк`}
                />
                <MetricCard
                  label="FBS/DBW"
                  value={formatNumber(kpis?.seller_stock_units)}
                  icon={Warehouse}
                  tone="teal"
                  note={`${formatNumber(kpis?.seller_warehouse_count)} складов`}
                />
                <MetricCard
                  label="Риск отмен"
                  value={formatNumber(kpis?.missed_orders_qty)}
                  icon={XCircle}
                  tone="red"
                  note={`${formatMoney(kpis?.missed_revenue)} · отмен ${formatNumber(kpis?.cancelled_orders_qty)}`}
                />
                <MetricCard
                  label="Остаток WB"
                  value={formatNumber(kpis?.stock_units)}
                  icon={Boxes}
                  tone="green"
                  note={`${formatNumber(kpis?.active_warehouses)} складов`}
                />
                <MetricCard
                  label="Приёмка"
                  value={formatNumber(kpis?.available_acceptance_slots)}
                  icon={PackageCheck}
                  tone="violet"
                  note="доступных слотов"
                />
                <MetricCard
                  label="Выкуп"
                  value={formatPercent(kpis?.buyout_percent)}
                  icon={ShieldCheck}
                  tone="teal"
                  note={`маржа ${formatPercent(kpis?.margin_percent)}`}
                />
              </div>

              {data.recommendations.length > 0 && (
                <RecommendationsPanel items={data.recommendations} />
              )}

              <Tabs defaultValue="tasks" className="w-full">
                <TabsList className="h-auto flex-wrap">
                  <TabsTrigger value="tasks" className="text-xs">
                    Задачи
                  </TabsTrigger>
                  <TabsTrigger value="builder" className="text-xs">
                    Подсортировщик
                  </TabsTrigger>
                  <TabsTrigger value="regional" className="text-xs">
                    Региональная отгрузка
                  </TabsTrigger>
                  <TabsTrigger value="warehouses" className="text-xs">
                    Склады
                  </TabsTrigger>
                  <TabsTrigger value="supplies" className="text-xs">
                    Поставки
                  </TabsTrigger>
                  <TabsTrigger value="details" className="text-xs">
                    Детализация
                  </TabsTrigger>
                  <TabsTrigger value="api" className="text-xs">
                    Интеграции WB
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="tasks" className="mt-4">
                  <LogisticsTasksWorkspace
                    tasks={tasks}
                    selectedTask={selectedTask}
                    selectedTaskId={selectedTask?.id ?? null}
                    products={products}
                    onSelectTask={(task) => {
                      setSelectedTaskId(task.id);
                      if (task.warehouse_name) {
                        setSelectedWarehouseName(task.warehouse_name);
                      }
                    }}
                    onExport={() => exportCsv("tasks")}
                    exporting={exportingDataset === "tasks"}
                  />
                </TabsContent>
                <TabsContent value="builder" className="mt-4">
                  <ShipmentBuilderWorkspace
                    rows={warehouses}
                    products={products}
                    supplies={data.supplies}
                    regionalShipments={regionalShipments}
                    periodDays={periodDays}
                    onSelectWarehouse={setSelectedWarehouseName}
                    onExport={() => exportCsv("shipment")}
                    exporting={exportingDataset === "shipment"}
                  />
                </TabsContent>
                <TabsContent value="regional" className="mt-4">
                  <RegionalShipmentsWorkspace
                    rows={regionalShipments}
                    onSelectWarehouse={setSelectedWarehouseName}
                    onExport={() => exportCsv("regional")}
                    exporting={exportingDataset === "regional"}
                  />
                </TabsContent>
                <TabsContent value="warehouses" className="mt-4">
                  <WarehouseManagementWorkspace
                    rows={warehouses}
                    supplies={data.supplies}
                    products={products}
                    controls={warehouseControls}
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
                    paidStorage={paidStorageDetails}
                    acceptance={acceptanceDetails}
                    transit={transitTariffs}
                    sellerWarehouses={sellerWarehouses}
                    onExport={exportCsv}
                    exportingDataset={exportingDataset}
                  />
                </TabsContent>
                <TabsContent value="api" className="mt-4">
                  <CapabilityTable rows={data.api_capabilities} />
                </TabsContent>
              </Tabs>

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px] 2xl:grid-cols-[minmax(0,1fr)_360px_380px]">
                <Card className="rounded-lg">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between gap-3">
                      <CardTitle className="text-base">
                        Деньги и расходы по складам
                      </CardTitle>
                      <Badge variant="outline" className="gap-1">
                        <Filter className="h-3.5 w-3.5" />
                        Первые {chartRows.length}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="h-[330px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={chartRows}
                          layout="vertical"
                          margin={{ left: 4, right: 18, top: 4, bottom: 4 }}
                        >
                          <CartesianGrid
                            strokeDasharray="3 3"
                            className="stroke-muted"
                          />
                          <XAxis
                            type="number"
                            tickLine={false}
                            axisLine={false}
                            tick={{ fontSize: 11 }}
                          />
                          <YAxis
                            dataKey="name"
                            type="category"
                            width={104}
                            tickLine={false}
                            axisLine={false}
                            tick={{ fontSize: 11 }}
                          />
                          <RechartsTooltip
                            formatter={(value: number, name: string) => [
                              formatMoney(value),
                              name === "revenue" ? "Выручка" : "Расходы",
                            ]}
                          />
                          <Bar dataKey="revenue" radius={[0, 4, 4, 0]}>
                            {chartRows.map((entry, index) => (
                              <Cell
                                key={`revenue-${index}`}
                                fill={
                                  entry.risk === "danger"
                                    ? "#ef4444"
                                    : "#2563eb"
                                }
                              />
                            ))}
                          </Bar>
                          <Bar
                            dataKey="costs"
                            radius={[0, 4, 4, 0]}
                            fill="#f97316"
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>

                <OperationalQueuePanel
                  rows={warehouses}
                  selectedName={selectedWarehouse?.warehouse_name ?? null}
                  periodDays={periodDays}
                  onSelect={setSelectedWarehouseName}
                />

                <SourceCoveragePanel
                  className="xl:col-span-2 2xl:col-span-1"
                  sources={data.data_sources}
                  capabilities={data.api_capabilities}
                />
              </div>
            </>
          )}
        </div>
      )}
    </PageShell>
  );
}

function LogisticsSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-8">
        {Array.from({ length: 8 }).map((_, index) => (
          <Skeleton key={index} className="h-24 rounded-lg" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Skeleton className="h-[380px] rounded-lg" />
        <Skeleton className="h-[380px] rounded-lg" />
      </div>
      <Skeleton className="h-[360px] rounded-lg" />
    </div>
  );
}

function MetricCard({
  label,
  value,
  note,
  icon: Icon,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  icon: LucideIcon;
  tone: "blue" | "orange" | "red" | "green" | "violet" | "teal";
}) {
  const toneMap = {
    blue: "bg-blue-50 text-blue-700 border-blue-200",
    orange: "bg-orange-50 text-orange-700 border-orange-200",
    red: "bg-red-50 text-red-700 border-red-200",
    green: "bg-emerald-50 text-emerald-700 border-emerald-200",
    violet: "bg-violet-50 text-violet-700 border-violet-200",
    teal: "bg-teal-50 text-teal-700 border-teal-200",
  };
  return (
    <Card className="rounded-lg">
      <CardContent className="flex h-24 flex-col justify-between p-4">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs font-medium text-muted-foreground">
            {label}
          </span>
          <span
            className={cn(
              "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
              toneMap[tone],
            )}
          >
            <Icon className="h-4 w-4" />
          </span>
        </div>
        <div className="min-w-0">
          <div className="truncate text-xl font-semibold tracking-normal">
            {value}
          </div>
          {note && (
            <div className="mt-1 truncate text-xs text-muted-foreground">
              {note}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function RecommendationsPanel({ items }: { items: RecommendationRow[] }) {
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      {items.slice(0, 3).map((item, index) => (
        <Alert
          key={`${item.title}-${index}`}
          className={severityClass(item.severity)}
        >
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle className="line-clamp-1">{item.title}</AlertTitle>
          <AlertDescription className="mt-1 space-y-2 text-sm">
            <p className="line-clamp-2">{item.detail}</p>
            <p className="font-medium">{item.action}</p>
          </AlertDescription>
        </Alert>
      ))}
    </div>
  );
}

function LogisticsTasksWorkspace({
  tasks,
  selectedTask,
  selectedTaskId,
  products,
  onSelectTask,
  onExport,
  exporting,
}: {
  tasks: LogisticsTaskRow[];
  selectedTask: LogisticsTaskRow | null;
  selectedTaskId: string | null;
  products: ProductRow[];
  onSelectTask: (task: LogisticsTaskRow) => void;
  onExport: () => void;
  exporting: boolean;
}) {
  const [analysisTask, setAnalysisTask] = useState<LogisticsTaskRow | null>(
    null,
  );
  const totals = tasks.reduce(
    (acc, task) => ({
      critical: acc.critical + (task.severity === "danger" ? 1 : 0),
      supply: acc.supply + task.recommended_supply_qty,
      potential: acc.potential + task.potential_revenue,
      net: acc.net + task.expected_net_effect,
    }),
    { critical: 0, supply: 0, potential: 0, net: 0 },
  );
  const selectedProducts = selectedTask
    ? relatedProductsForTask(products, selectedTask)
    : [];
  const analysisProducts = analysisTask
    ? relatedProductsForTask(products, analysisTask)
    : [];

  if (!tasks.length) {
    return (
      <Alert>
        <ClipboardList className="h-4 w-4" />
        <AlertTitle>Задач по логистике нет</AlertTitle>
        <AlertDescription>
          Когда появится дефицит, высокий расход логистики, низкий выкуп или
          закрытая приёмка, модуль соберёт задачи здесь.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_430px]">
        <div className="space-y-3">
          <Card className="rounded-lg">
            <CardContent className="grid gap-0 p-0 sm:grid-cols-4 sm:divide-x">
              <DetailStat
                label="Активные задачи"
                value={formatNumber(tasks.length)}
                icon={ClipboardList}
              />
              <DetailStat
                label="Критичные"
                value={formatNumber(totals.critical)}
                icon={AlertTriangle}
              />
              <DetailStat
                label="К отгрузке"
                value={`+${formatNumber(totals.supply)}`}
                icon={PackagePlus}
              />
              <DetailStat
                label="Чистый эффект"
                value={formatMoney(totals.net)}
                icon={CircleDollarSign}
              />
            </CardContent>
          </Card>

          <Card className="rounded-lg">
            <CardHeader className="border-b pb-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-base">Задачи на сегодня</CardTitle>
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
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y">
                {tasks.map((task) => {
                  const selected = task.id === selectedTaskId;
                  return (
                    <button
                      key={task.id}
                      type="button"
                      onClick={() => onSelectTask(task)}
                      className={cn(
                        "grid w-full gap-2 overflow-hidden px-4 py-3 text-left transition hover:bg-muted/50",
                        selected && "bg-primary/5",
                      )}
                    >
                      <span className="flex items-start justify-between gap-3">
                        <span className="min-w-0">
                          <span className="block truncate font-medium">
                            {task.title}
                          </span>
                          <span className="mt-1 block truncate text-xs text-muted-foreground">
                            {task.region_name ||
                              task.warehouse_name ||
                              "общий контур"}
                          </span>
                        </span>
                        <span className="shrink-0">
                          <RiskBadge level={task.severity} />
                        </span>
                      </span>
                      <span className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
                        <span className="min-w-0">
                          <span className="block text-muted-foreground">
                            Потенциал
                          </span>
                          <span className="block truncate font-semibold">
                            {formatMoney(task.potential_revenue)}
                          </span>
                        </span>
                        <span className="min-w-0">
                          <span className="block text-muted-foreground">
                            Поставка
                          </span>
                          <span className="block truncate font-semibold">
                            +{formatNumber(task.recommended_supply_qty)}
                          </span>
                        </span>
                        <span className="min-w-0 sm:text-right">
                          <span className="block text-muted-foreground">
                            Чистый эффект
                          </span>
                          <span className="block truncate font-semibold">
                            {formatMoney(task.expected_net_effect)}
                          </span>
                        </span>
                      </span>
                      <span className="flex flex-wrap gap-1">
                        {task.tags.slice(0, 5).map((tag) => (
                          <Badge
                            key={tag}
                            variant="outline"
                            className="text-[10px]"
                          >
                            {tag}
                          </Badge>
                        ))}
                      </span>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>

        {selectedTask && (
          <TaskDetailPanel
            task={selectedTask}
            products={selectedProducts}
            onAnalyze={() => setAnalysisTask(selectedTask)}
          />
        )}
      </div>
      <TaskAnalysisSheet
        task={analysisTask}
        products={analysisProducts}
        open={Boolean(analysisTask)}
        onOpenChange={(open) => {
          if (!open) setAnalysisTask(null);
        }}
      />
    </>
  );
}

function TaskDetailPanel({
  task,
  products,
  onAnalyze,
}: {
  task: LogisticsTaskRow;
  products: ProductRow[];
  onAnalyze: () => void;
}) {
  return (
    <Card className="rounded-lg xl:sticky xl:top-20 xl:self-start">
      <CardHeader className="border-b pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="truncate text-base">{task.title}</CardTitle>
            <div className="mt-1 flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
              <MapPin className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">
                {task.warehouse_name || task.region_name || "общий контур"}
              </span>
            </div>
          </div>
          <RiskBadge level={task.severity} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <div className="grid grid-cols-2 gap-3">
          <CompactFact
            label="Потенциал"
            value={formatMoney(task.potential_revenue)}
            note={`${formatNumber(task.potential_orders_qty)} заказов`}
          />
          <CompactFact
            label="Чистый эффект"
            value={formatMoney(task.expected_net_effect)}
            note={confidenceLabel(task.confidence)}
          />
          <CompactFact
            label="К поставке"
            value={`+${formatNumber(task.recommended_supply_qty)}`}
            note={
              task.forecast_days ? `${task.forecast_days} дней` : "по факту"
            }
          />
          <CompactFact
            label="Дефицит через"
            value={
              task.stockout_in_days == null
                ? "—"
                : `${formatNumber(task.stockout_in_days)} дн.`
            }
            note={`лог. ${formatPercent(task.logistics_share_percent)}`}
          />
        </div>

        <Alert className={severityClass(task.severity)}>
          <Gauge className="h-4 w-4" />
          <AlertTitle>Что происходит</AlertTitle>
          <AlertDescription className="mt-1 text-sm">
            {task.detail}
          </AlertDescription>
        </Alert>

        <div className="rounded-md border bg-muted/20 p-3">
          <div className="text-xs font-medium text-muted-foreground">
            Действие
          </div>
          <div className="mt-1 text-sm font-medium">{task.action}</div>
        </div>

        {task.task_type === "buyout_drop" && (
          <div className="space-y-2">
            <div className="text-sm font-medium">Анализ причин</div>
            {task.tags.map((tag, index) => (
              <div
                key={`${tag}-${index}`}
                className="grid grid-cols-[auto_1fr] gap-3 rounded-md border px-3 py-2 text-sm"
              >
                <span
                  className={cn(
                    "mt-1 h-2 w-2 rounded-full",
                    reasonDotClass(tag),
                  )}
                />
                <span>
                  <span className="block font-medium">{tag}</span>
                  <span className="block text-xs text-muted-foreground">
                    {buyoutReasonCopy(tag)}
                  </span>
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-1.5">
          {task.tags.map((tag) => (
            <Badge key={tag} variant="outline">
              {tag}
            </Badge>
          ))}
        </div>

        {products.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2 text-sm font-medium">
              <span>Артикулы в задаче</span>
              <Badge variant="outline">{formatNumber(products.length)}</Badge>
            </div>
            <ProductMiniTable products={products.slice(0, 5)} compact />
          </div>
        )}

        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
          <Button size="sm" className="gap-2" onClick={onAnalyze}>
            <PanelRightOpen className="h-4 w-4" />
            Анализ
          </Button>
          <Button asChild size="sm" variant="outline" className="gap-2">
            <Link to="/stock-control">
              <PackagePlus className="h-4 w-4" />
              Отгрузка
              <ArrowUpRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
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
      <SheetContent className="flex w-full flex-col overflow-hidden p-0 sm:max-w-[min(1060px,calc(100vw-2rem))]">
        <div className="border-b px-5 py-4">
          <SheetHeader className="pr-8 text-left">
            <div className="flex flex-wrap items-center gap-2">
              {task && <RiskBadge level={task.severity} />}
              <Badge variant="outline" className="gap-1">
                <Info className="h-3.5 w-3.5" />
                {task ? taskTypeLabel(task.task_type) : "анализ"}
              </Badge>
            </div>
            <SheetTitle className="break-words text-lg">
              {task?.title || "Анализ задачи"}
            </SheetTitle>
            <SheetDescription>
              {task?.warehouse_name || task?.region_name || "общий контур"}
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
                  label="14 дней"
                  value={`+${formatNumber(totals.supply14)}`}
                  note="быстрый довоз"
                />
                <CompactFact
                  label="30 дней"
                  value={`+${formatNumber(totals.supply30)}`}
                  note="плановая поставка"
                />
                <CompactFact
                  label="Чистый эффект"
                  value={formatMoney(task?.expected_net_effect ?? totals.net)}
                  note={confidenceLabel(task?.confidence || "medium")}
                />
              </div>

              {task && (
                <Alert className={severityClass(task.severity)}>
                  <Gauge className="h-4 w-4" />
                  <AlertTitle>Причина</AlertTitle>
                  <AlertDescription className="mt-1 text-sm">
                    {task.detail}
                  </AlertDescription>
                </Alert>
              )}

              <ProductMiniTable products={products.slice(0, 24)} />
            </div>

            <div className="space-y-3">
              <div className="rounded-lg border bg-background p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium">
                  <Calculator className="h-4 w-4 text-muted-foreground" />
                  Расчёт
                </div>
                <div className="space-y-3 text-sm">
                  <FormulaLine
                    label="Покрытие 14"
                    value="max(продаж/день × 14 − остаток, 0)"
                  />
                  <FormulaLine
                    label="Покрытие 30"
                    value="max(продаж/день × 30 − остаток, 0)"
                  />
                  <FormulaLine
                    label="Чистый эффект"
                    value="потенциал × маржа − логистика на поставку"
                  />
                  <FormulaLine
                    label="Логистика"
                    value="доставка + возвраты + хранение + приёмка"
                  />
                </div>
              </div>

              <div className="rounded-lg border bg-muted/20 p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium">
                  <ListChecks className="h-4 w-4 text-muted-foreground" />
                  Действие
                </div>
                <div className="text-sm">{task?.action}</div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {(task?.tags ?? []).map((tag) => (
                    <Badge key={tag} variant="outline">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function ShipmentBuilderWorkspace({
  rows,
  products,
  supplies,
  regionalShipments,
  periodDays,
  onSelectWarehouse,
  onExport,
  exporting,
}: {
  rows: WarehouseRow[];
  products: ProductRow[];
  supplies: SupplyRow[];
  regionalShipments: RegionalShipmentRow[];
  periodDays: number;
  onSelectWarehouse: (warehouseName: string) => void;
  onExport: () => void;
  exporting: boolean;
}) {
  const [mode, setMode] = useState<ShipmentBuilderMode>("warehouse");
  const [targetDays, setTargetDays] = useState(45);
  const [minQty, setMinQty] = useState(1);
  const [boxMultiple, setBoxMultiple] = useState(1);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [excludedIds, setExcludedIds] = useState<Set<string>>(() => new Set());
  const [shipmentSorting, setShipmentSorting] = useState<SortingState>([
    { id: "shipmentNet", desc: true },
  ]);

  const options = useMemo(() => {
    if (mode === "region") {
      const names = Array.from(
        new Set(
          rows
            .map((row) => row.region_name)
            .filter((name): name is string => Boolean(name)),
        ),
      );
      return names.length ? names : ["регион не определён"];
    }
    return rows.map((row) => row.warehouse_name);
  }, [mode, rows]);

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
    return sortProductRows(filtered).slice(0, 80);
  }, [effectiveKey, mode, products]);

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

  const relatedSupplies = supplies
    .filter((supply) =>
      mode === "region"
        ? rows.some(
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

  const topRoutes = regionalShipments.length
    ? regionalShipments.slice(0, 3)
    : rows
        .map((row) => ({
          id: row.warehouse_name,
          warehouse_name: row.warehouse_name,
          region_name: row.region_name,
          recommended_supply_qty: calculateWarehouse(row, periodDays)
            .replenishmentQty,
          expected_net_effect: row.missed_revenue,
          priority: row.risk_level === "danger" ? "recommended" : "planned",
        }))
        .sort((a, b) => b.expected_net_effect - a.expected_net_effect)
        .slice(0, 3);

  const toggleLine = useCallback((id: string, checked: boolean) => {
    setExcludedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const shipmentChartRows = useMemo(
    () =>
      selectedLines
        .slice()
        .sort((a, b) => b.shipmentNet - a.shipmentNet)
        .slice(0, 8)
        .map((row) => ({
          name: compactProduct(productLabel(row)),
          qty: row.shipmentQty,
          net: Math.round(row.shipmentNet),
          risk: row.risk_level,
        })),
    [selectedLines],
  );

  const shipmentColumns = useMemo<ColumnDef<ShipmentLine>[]>(
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
              {row.original.warehouse_name} · WB {row.original.nm_id ?? "—"}
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
          <div className="text-right">
            <div className="font-medium">
              {formatNumber(row.original.stock_units)}
            </div>
            <div className="text-xs text-muted-foreground">
              {row.original.turnover_days
                ? `${formatNumber(row.original.turnover_days)} дн.`
                : "—"}
            </div>
          </div>
        ),
      },
      {
        id: "avg_daily_sales",
        accessorFn: (row) => row.avg_daily_sales,
        header: ({ column }) => (
          <SortableHeader column={column} label="Скорость" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right font-medium">
            {formatNumber(row.original.avg_daily_sales)}
          </div>
        ),
      },
      {
        id: "targetStock",
        accessorFn: (row) => row.targetStock,
        header: ({ column }) => (
          <SortableHeader column={column} label="Цель" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right font-medium">
            {formatNumber(row.original.targetStock)}
          </div>
        ),
      },
      {
        id: "shipmentQty",
        accessorFn: (row) => row.shipmentQty,
        header: ({ column }) => (
          <SortableHeader column={column} label="Отгрузка" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right font-semibold">
            +{formatNumber(row.original.shipmentQty)}
          </div>
        ),
      },
      {
        id: "shipmentNet",
        accessorFn: (row) => row.shipmentNet,
        header: ({ column }) => (
          <SortableHeader column={column} label="Чистый эффект" align="right" />
        ),
        cell: ({ row }) => (
          <div className="text-right">
            <div className="font-semibold">
              {formatMoney(row.original.shipmentNet)}
            </div>
            <div className="text-xs text-muted-foreground">
              {formatMoney(row.original.shipmentRevenue)}
            </div>
          </div>
        ),
      },
    ],
    [toggleLine],
  );

  const shipmentTable = useReactTable({
    data: visibleLines,
    columns: shipmentColumns,
    state: { sorting: shipmentSorting },
    onSortingChange: setShipmentSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const sortedShipmentRows = shipmentTable
    .getRowModel()
    .rows.map((row) => row.original);

  if (!products.length) {
    return (
      <Alert>
        <PackageSearch className="h-4 w-4" />
        <AlertTitle>Данных по артикулам пока нет</AlertTitle>
        <AlertDescription>
          После синхронизации заказов, продаж, финансов и остатков здесь
          появится подсортировщик на уровне товара.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="space-y-3">
        <Card className="rounded-lg">
          <CardContent className="grid gap-0 p-0 sm:grid-cols-4 sm:divide-x">
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
          </CardContent>
        </Card>

        <Card className="rounded-lg">
          <CardHeader className="border-b pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <CardTitle className="text-base">
                  Подсортировщик артикулов
                </CardTitle>
                <div className="mt-1 text-xs text-muted-foreground">
                  {effectiveKey || "нет направления"} · {targetDays} дней
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
                Экспорт
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {shipmentChartRows.length > 0 && (
              <div className="border-b p-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-medium">
                      Отгрузка по выгоде
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Показывает выбранные позиции с самым высоким чистым
                      эффектом.
                    </div>
                  </div>
                  <Badge variant="outline">
                    выбрано {formatNumber(totals.sku)}
                  </Badge>
                </div>
                <div className="h-[230px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={shipmentChartRows}
                      layout="vertical"
                      margin={{ left: 0, right: 16, top: 4, bottom: 4 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        className="stroke-muted"
                      />
                      <XAxis
                        type="number"
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 11 }}
                      />
                      <YAxis
                        dataKey="name"
                        type="category"
                        width={112}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 11 }}
                      />
                      <RechartsTooltip
                        formatter={(value: number, name: string) => [
                          name === "net"
                            ? formatMoney(value)
                            : formatNumber(value),
                          name === "net" ? "Чистый эффект" : "К отгрузке",
                        ]}
                      />
                      <Bar dataKey="net" radius={[0, 4, 4, 0]}>
                        {shipmentChartRows.map((entry, index) => (
                          <Cell
                            key={`shipment-net-${index}`}
                            fill={
                              entry.risk === "danger"
                                ? "#ef4444"
                                : entry.risk === "warning"
                                  ? "#f97316"
                                  : "#10b981"
                            }
                          />
                        ))}
                      </Bar>
                      <Bar dataKey="qty" radius={[0, 4, 4, 0]} fill="#2563eb" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
            <div className="divide-y md:hidden">
              {sortedShipmentRows.map((row) => (
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
                  {shipmentTable.getHeaderGroups().map((headerGroup) => (
                    <TableRow key={headerGroup.id}>
                      {headerGroup.headers.map((header) => (
                        <TableHead
                          key={header.id}
                          className={cn(
                            header.id === "selected" && "w-9",
                            header.id === "product" && "min-w-[190px]",
                            header.id === "risk" && "w-[90px]",
                            [
                              "stock_units",
                              "avg_daily_sales",
                              "targetStock",
                              "shipmentQty",
                            ].includes(header.id) && "w-[86px] text-right",
                            header.id === "shipmentNet" &&
                              "w-[112px] text-right",
                            [
                              "stock_units",
                              "avg_daily_sales",
                              "targetStock",
                              "shipmentQty",
                              "shipmentNet",
                            ].includes(header.id) && "text-right",
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
                  {shipmentTable.getRowModel().rows.map((row) => (
                    <TableRow key={row.id}>
                      {row.getVisibleCells().map((cell) => (
                        <TableCell
                          key={cell.id}
                          className={cn(
                            cell.column.id === "selected" && "w-9",
                            cell.column.id === "risk" && "w-[90px]",
                            cell.column.id === "product" && "min-w-[190px]",
                            [
                              "stock_units",
                              "avg_daily_sales",
                              "targetStock",
                              "shipmentQty",
                            ].includes(cell.column.id) && "w-[86px] text-right",
                            cell.column.id === "shipmentNet" &&
                              "w-[112px] text-right",
                            [
                              "stock_units",
                              "avg_daily_sales",
                              "targetStock",
                              "shipmentQty",
                              "shipmentNet",
                            ].includes(cell.column.id) && "text-right",
                          )}
                        >
                          {flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext(),
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-3 xl:sticky xl:top-20 xl:self-start">
        <Card className="rounded-lg">
          <CardHeader className="border-b pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Settings2 className="h-4 w-4" />
              Настройки
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 p-4">
            <div className="grid grid-cols-2 gap-2 rounded-md bg-muted p-1">
              <Button
                size="sm"
                variant={mode === "warehouse" ? "default" : "ghost"}
                onClick={() => setMode("warehouse")}
                className="h-8 gap-2"
              >
                <Warehouse className="h-4 w-4" />
                Склад
              </Button>
              <Button
                size="sm"
                variant={mode === "region" ? "default" : "ghost"}
                onClick={() => setMode("region")}
                className="h-8 gap-2"
              >
                <MapPin className="h-4 w-4" />
                Регион
              </Button>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="font-medium">Покрытие</span>
                <Badge variant="outline">{targetDays} дней</Badge>
              </div>
              <Slider
                min={28}
                max={90}
                step={1}
                value={[targetDays]}
                onValueChange={(value) => setTargetDays(value[0] ?? 45)}
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
                    setMinQty(Math.max(Number(event.target.value) || 1, 1))
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
                    setBoxMultiple(Math.max(Number(event.target.value) || 1, 1))
                  }
                  className="h-8"
                />
              </label>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-lg">
          <CardHeader className="border-b pb-3">
            <CardTitle className="text-base">Направления</CardTitle>
          </CardHeader>
          <CardContent className="max-h-[260px] space-y-2 overflow-y-auto p-3">
            {options.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => {
                  setSelectedKey(option);
                  if (mode === "warehouse") onSelectWarehouse(option);
                }}
                className={cn(
                  "flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left text-sm transition hover:bg-muted/60",
                  option === effectiveKey && "border-primary bg-primary/5",
                )}
              >
                <span className="min-w-0 truncate">{option}</span>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </button>
            ))}
          </CardContent>
        </Card>

        <Card className="rounded-lg">
          <CardHeader className="border-b pb-3">
            <CardTitle className="text-base">Лучшие слоты</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 p-3">
            {topRoutes.map((route) => (
              <button
                key={route.id}
                type="button"
                className="grid w-full grid-cols-[1fr_auto] gap-3 rounded-md border px-3 py-2 text-left text-sm hover:bg-muted/60"
                onClick={() => onSelectWarehouse(route.warehouse_name)}
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">
                    {route.warehouse_name}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {route.region_name || "регион не определён"}
                  </span>
                </span>
                <span className="text-right text-xs">
                  <span className="block font-medium">
                    +{formatNumber(route.recommended_supply_qty)}
                  </span>
                  <span className="block text-muted-foreground">
                    {formatMoney(route.expected_net_effect)}
                  </span>
                </span>
              </button>
            ))}
          </CardContent>
        </Card>

        {relatedSupplies.length > 0 && (
          <Card className="rounded-lg">
            <CardHeader className="border-b pb-3">
              <CardTitle className="text-base">В пути</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 p-3">
              {relatedSupplies.map((supply) => (
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
        )}
      </div>
    </div>
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
        <MetricInline
          label="Чистый эффект"
          value={formatMoney(row.shipmentNet)}
        />
      </div>
    </div>
  );
}

function RegionalShipmentsWorkspace({
  rows,
  onSelectWarehouse,
  onExport,
  exporting,
}: {
  rows: RegionalShipmentRow[];
  onSelectWarehouse: (warehouseName: string) => void;
  onExport: () => void;
  exporting: boolean;
}) {
  const totals = rows.reduce(
    (acc, row) => ({
      qty: acc.qty + row.recommended_supply_qty,
      revenue: acc.revenue + row.potential_revenue,
      net: acc.net + row.expected_net_effect,
      blocked: acc.blocked + (row.priority === "blocked" ? 1 : 0),
    }),
    { qty: 0, revenue: 0, net: 0, blocked: 0 },
  );

  if (!rows.length) {
    return (
      <Alert>
        <Layers3 className="h-4 w-4" />
        <AlertTitle>Региональных отгрузок нет</AlertTitle>
        <AlertDescription>
          Пока нет складов, где прогноз спроса и экономика дают смысл для
          подсортировки.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      <Card className="rounded-lg">
        <CardContent className="grid gap-0 p-0 sm:grid-cols-4 sm:divide-x">
          <DetailStat
            label="Направлений"
            value={formatNumber(rows.length)}
            icon={Layers3}
          />
          <DetailStat
            label={`${PRODUCTION_PLANNING_DAYS} дн. план`}
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
            icon={CircleDollarSign}
          />
        </CardContent>
      </Card>

      <Card className="rounded-lg">
        <CardHeader className="border-b pb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-base">Региональная отгрузка</CardTitle>
              {totals.blocked > 0 && (
                <Badge
                  variant="outline"
                  className="border-red-200 bg-red-50 text-red-700"
                >
                  {formatNumber(totals.blocked)} без слота
                </Badge>
              )}
            </div>
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
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y">
            {rows.map((row) => (
              <button
                key={row.id}
                type="button"
                className="grid w-full gap-3 px-4 py-3 text-left transition hover:bg-muted/50 lg:grid-cols-[minmax(0,1.6fr)_repeat(5,minmax(105px,0.7fr))_auto] lg:items-center"
                onClick={() => onSelectWarehouse(row.warehouse_name)}
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">
                    {row.warehouse_name}
                  </span>
                  <span className="mt-1 block truncate text-xs text-muted-foreground">
                    {row.reason}
                  </span>
                </span>
                <MetricInline
                  label="Поставка"
                  value={`+${formatNumber(row.recommended_supply_qty)}`}
                />
                <MetricInline
                  label="Потенциал"
                  value={formatMoney(row.potential_revenue)}
                />
                <MetricInline
                  label="Спрос WB"
                  value={`${formatNumber(row.region_sales_qty)} шт`}
                />
                <MetricInline
                  label="Чистый эффект"
                  value={formatMoney(row.expected_net_effect)}
                />
                <MetricInline
                  label="Приёмка"
                  value={acceptanceLabel(row.acceptance_status)}
                  align="left"
                />
                <span className="flex items-center justify-end gap-2">
                  <PriorityBadge priority={row.priority} />
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </span>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function WarehouseManagementWorkspace({
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
  return (
    <div className="space-y-4">
      <WarehouseControlsPanel
        rows={controls}
        disabledWarehouses={disabledWarehouses}
        onToggleWarehouse={onToggleWarehouse}
        onExport={onExport}
        exporting={exporting}
      />
      <WarehouseWorkspace
        rows={rows}
        supplies={supplies}
        products={products}
        selectedWarehouse={selectedWarehouse}
        selectedName={selectedName}
        periodDays={periodDays}
        onSelect={onSelect}
      />
    </div>
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
    <Card className="rounded-lg">
      <CardHeader className="border-b pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">Управление складами</CardTitle>
            <div className="mt-1 text-xs text-muted-foreground">
              Отключённые склады не участвуют в локальном списке задач и
              региональных отгрузок.
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
            Экспорт
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid divide-y lg:grid-cols-2 lg:divide-x lg:divide-y-0">
          {rows.slice(0, 8).map((row) => {
            const enabled = !disabledWarehouses.has(row.warehouse_name);
            return (
              <div
                key={row.warehouse_name}
                className="grid gap-3 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium">
                      {row.warehouse_name}
                    </span>
                    <WarehouseModeBadge mode={row.recommended_mode} />
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                    {row.reason}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Badge variant="outline">
                      {formatNumber(row.task_count)} задач
                    </Badge>
                    <Badge variant="outline">
                      {formatMoney(row.potential_revenue)}
                    </Badge>
                    <StatusBadge status={row.acceptance_status} />
                  </div>
                </div>
                <div className="flex items-center justify-between gap-3 sm:flex-col sm:items-end">
                  <span className="text-xs text-muted-foreground">
                    {enabled ? "Активен" : "Отключён"}
                  </span>
                  <Switch
                    checked={enabled}
                    onCheckedChange={() =>
                      onToggleWarehouse(row.warehouse_name)
                    }
                    aria-label={`Переключить задачи склада ${row.warehouse_name}`}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function OperationalQueuePanel({
  rows,
  selectedName,
  periodDays,
  onSelect,
}: {
  rows: WarehouseRow[];
  selectedName: string | null;
  periodDays: number;
  onSelect: (name: string) => void;
}) {
  const candidates = rows.filter((row) => row.risk_level !== "ok").slice(0, 5);
  const visibleRows = candidates.length ? candidates : rows.slice(0, 5);

  return (
    <Card className="rounded-lg">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Операционный план</CardTitle>
          <Badge variant="outline" className="gap-1">
            <ClipboardList className="h-3.5 w-3.5" />
            {visibleRows.length}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {visibleRows.map((row) => {
          const calc = calculateWarehouse(row, periodDays);
          const selected = row.warehouse_name === selectedName;
          return (
            <button
              key={row.warehouse_name}
              type="button"
              onClick={() => onSelect(row.warehouse_name)}
              className={cn(
                "flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left transition hover:bg-muted/60",
                selected && "border-primary bg-primary/5",
              )}
            >
              <span
                className={cn(
                  "mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full",
                  riskDotClass(row.risk_level),
                )}
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">
                    {row.warehouse_name}
                  </span>
                  <span className="shrink-0 text-xs font-medium text-muted-foreground">
                    {calc.priority}
                  </span>
                </span>
                <span className="mt-1 grid grid-cols-3 gap-2 text-xs text-muted-foreground">
                  <span className="truncate">
                    риск {formatMoney(row.missed_revenue)}
                  </span>
                  <span className="truncate">
                    лог. {formatPercent(row.logistics_share_percent)}
                  </span>
                  <span className="truncate text-right">
                    +{formatNumber(calc.replenishmentQty)}
                  </span>
                </span>
              </span>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}

function SourceCoveragePanel({
  sources,
  capabilities,
  className,
}: {
  sources: DataSourceRow[];
  capabilities: CapabilityRow[];
  className?: string;
}) {
  const okCount = sources.filter((source) => source.status === "ok").length;
  const pct = sources.length ? (okCount / sources.length) * 100 : 0;
  return (
    <Card className={cn("rounded-lg", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Покрытие данных</CardTitle>
          <Badge variant="outline">{formatPercent(pct, 0)}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <Progress value={pct} className="h-2" />
        <div className="space-y-2">
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
        <div className="rounded-md border bg-muted/30 px-3 py-2">
          <div className="mb-2 flex items-center justify-between gap-2 text-sm font-medium">
            <span>API подключены</span>
            <span className="text-muted-foreground">
              {capabilities.filter((item) => item.status === "active").length}/
              {capabilities.length}
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {capabilities.map((item) => (
              <Badge
                key={item.key}
                variant="outline"
                className={cn(
                  "max-w-full gap-1",
                  item.status === "active"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "border-amber-200 bg-amber-50 text-amber-700",
                )}
              >
                {item.status === "active" ? (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                ) : (
                  <Clock className="h-3.5 w-3.5" />
                )}
                <span className="truncate">{item.token_category}</span>
              </Badge>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function WarehouseWorkspace({
  rows,
  supplies,
  products,
  selectedWarehouse,
  selectedName,
  periodDays,
  onSelect,
}: {
  rows: WarehouseRow[];
  supplies: SupplyRow[];
  products: ProductRow[];
  selectedWarehouse: WarehouseRow | null;
  selectedName: string | null;
  periodDays: number;
  onSelect: (name: string) => void;
}) {
  if (!rows.length) {
    return (
      <Alert>
        <PackageSearch className="h-4 w-4" />
        <AlertTitle>Складов пока нет</AlertTitle>
        <AlertDescription>
          После синхронизации остатков, заказов, продаж и тарифов здесь появится
          карта складской экономики.
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_430px]">
      <WarehouseTable
        rows={rows}
        selectedName={selectedName}
        periodDays={periodDays}
        onSelect={onSelect}
      />
      {selectedWarehouse && (
        <WarehouseDetailPanel
          row={selectedWarehouse}
          supplies={supplies}
          products={products.filter(
            (product) =>
              product.warehouse_name === selectedWarehouse.warehouse_name,
          )}
          periodDays={periodDays}
        />
      )}
    </div>
  );
}

function WarehouseTable({
  rows,
  selectedName,
  periodDays,
  onSelect,
}: {
  rows: WarehouseRow[];
  selectedName: string | null;
  periodDays: number;
  onSelect: (name: string) => void;
}) {
  return (
    <Card className="rounded-lg">
      <CardContent className="p-0">
        <div className="divide-y md:hidden">
          {rows.map((row) => {
            const calc = calculateWarehouse(row, periodDays);
            const selected = row.warehouse_name === selectedName;
            return (
              <button
                key={row.warehouse_name}
                type="button"
                onClick={() => onSelect(row.warehouse_name)}
                className={cn(
                  "grid w-full gap-3 px-3 py-3 text-left transition hover:bg-muted/50",
                  selected && "bg-primary/5",
                )}
              >
                <span className="flex items-start justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2">
                    <Warehouse className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">
                        {row.warehouse_name}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {row.region_name || "регион не определён"}
                      </span>
                    </span>
                  </span>
                  <RiskBadge level={row.risk_level} />
                </span>
                <span className="grid grid-cols-3 gap-2 text-xs">
                  <span className="min-w-0">
                    <span className="block text-muted-foreground">Остаток</span>
                    <span className="block truncate font-semibold">
                      {formatNumber(row.stock_units)}
                    </span>
                    <span className="block truncate text-muted-foreground">
                      {row.turnover_days
                        ? `${formatNumber(row.turnover_days)} дн.`
                        : "—"}
                    </span>
                  </span>
                  <span className="min-w-0">
                    <span className="block text-muted-foreground">Деньги</span>
                    <span className="block truncate font-semibold">
                      {formatMoney(row.revenue)}
                    </span>
                    <span className="block truncate text-muted-foreground">
                      риск {formatMoney(row.missed_revenue)}
                    </span>
                  </span>
                  <span className="min-w-0 text-right">
                    <span className="block text-muted-foreground">План</span>
                    <span className="block truncate font-semibold">
                      +{formatNumber(calc.replenishmentQty)}
                    </span>
                    <span className="block truncate text-muted-foreground">
                      лог. {formatPercent(row.logistics_share_percent)}
                    </span>
                  </span>
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
                <TableHead className="text-right">Приёмка</TableHead>
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
                      <div className="font-medium">
                        {formatNumber(row.stock_units)}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {row.turnover_days
                          ? `${formatNumber(row.turnover_days)} дн.`
                          : "—"}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="font-medium">
                        {formatNumber(row.orders_qty)}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        −{formatNumber(row.missed_orders_qty)}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="font-medium">
                        {formatMoney(row.revenue)}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {row.revenue_source === "finance"
                          ? `финансы · ${formatNumber(row.finance_rows)} строк`
                          : `выкуп ${formatPercent(row.buyout_percent)}`}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="font-medium">
                        {formatMoney(calc.totalLogistics)}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {formatMoney(calc.costPerOrder)} / заказ
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="font-medium">
                        {formatPercent(row.margin_percent)}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {formatMoney(calc.marginAfterLogistics)}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <StatusBadge status={row.acceptance_status} />
                      <div className="mt-1 text-xs text-muted-foreground">
                        k={row.acceptance_coefficient ?? "—"}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="font-medium">
                        +{formatNumber(calc.replenishmentQty)}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {FAST_REPLENISHMENT_DAYS} дн.
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <ChevronRight
                        className={cn(
                          "ml-auto h-4 w-4 text-muted-foreground",
                          selected && "text-primary",
                        )}
                      />
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

function WarehouseDetailPanel({
  row,
  supplies,
  products,
  periodDays,
}: {
  row: WarehouseRow;
  supplies: SupplyRow[];
  products: ProductRow[];
  periodDays: number;
}) {
  const calc = calculateWarehouse(row, periodDays);
  const relatedSupplies = supplies
    .filter((supply) =>
      [supply.actual_warehouse_name, supply.warehouse_name].some(
        (name) => name && name === row.warehouse_name,
      ),
    )
    .slice(0, 4);

  return (
    <Card className="rounded-lg xl:sticky xl:top-20 xl:self-start">
      <CardHeader className="border-b pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="truncate text-base">
              {row.warehouse_name}
            </CardTitle>
            <div className="mt-1 flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
              <MapPin className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">
                {row.region_name || "регион не определён"}
              </span>
            </div>
          </div>
          <RiskBadge level={row.risk_level} />
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid grid-cols-2 divide-x divide-y border-b text-sm">
          <DetailStat
            label="Риск потери"
            value={formatMoney(row.missed_revenue)}
            icon={TrendingDown}
          />
          <DetailStat
            label="К заказу"
            value={`+${formatNumber(calc.replenishmentQty)}`}
            icon={PackagePlus}
          />
          <DetailStat
            label="Лог/заказ"
            value={formatMoney(calc.costPerOrder)}
            icon={Calculator}
          />
          <DetailStat
            label="Прибыль"
            value={formatMoney(calc.marginAfterLogistics)}
            icon={CircleDollarSign}
          />
        </div>

        <Tabs defaultValue="economics" className="w-full">
          <TabsList className="m-3 grid h-auto grid-cols-5">
            <TabsTrigger value="economics" className="px-2 text-xs">
              Деньги
            </TabsTrigger>
            <TabsTrigger value="stock" className="px-2 text-xs">
              Остатки
            </TabsTrigger>
            <TabsTrigger value="sku" className="px-2 text-xs">
              Артикулы
            </TabsTrigger>
            <TabsTrigger value="acceptance" className="px-2 text-xs">
              Слоты
            </TabsTrigger>
            <TabsTrigger value="plan" className="px-2 text-xs">
              План
            </TabsTrigger>
          </TabsList>

          <TabsContent value="economics" className="m-0 space-y-3 px-4 pb-4">
            <div className="grid grid-cols-2 gap-3">
              <CompactFact
                label="Выручка"
                value={formatMoney(row.revenue)}
                note={
                  row.revenue_source === "finance"
                    ? `финансы · ${formatNumber(row.finance_rows)} строк`
                    : `${formatNumber(row.sales_qty)} продаж`
                }
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
                label="Лог/продажа"
                value={formatMoney(calc.costPerSale)}
                note={formatPercent(row.logistics_share_percent)}
              />
            </div>
            <div className="space-y-2">
              <CostLine
                label="Логистика"
                value={row.logistics_cost}
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
              <CostLine
                label="Возвратная логистика"
                value={row.return_logistics_cost}
                total={calc.totalLogistics}
              />
            </div>
          </TabsContent>

          <TabsContent value="stock" className="m-0 space-y-3 px-4 pb-4">
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
                label="На WB"
                value={formatNumber(row.stock_units)}
                note="единиц"
              />
              <CompactFact
                label="В пути клиенту"
                value={formatNumber(row.in_way_to_client)}
                note="единиц"
              />
              <CompactFact
                label="Возвраты в пути"
                value={formatNumber(row.in_way_from_client)}
                note="единиц"
              />
              <CompactFact
                label={`${FAST_REPLENISHMENT_DAYS} дн. цель`}
                value={formatNumber(calc.targetStock)}
                note={`${formatNumber(calc.avgDailySales)} / день`}
              />
            </div>
          </TabsContent>

          <TabsContent value="sku" className="m-0 space-y-3 px-4 pb-4">
            <div className="grid grid-cols-2 gap-3">
              <CompactFact
                label="Артикулы"
                value={formatNumber(products.length)}
                note="на складе"
              />
              <CompactFact
                label="К отгрузке"
                value={`+${formatNumber(
                  products.reduce(
                    (acc, product) => acc + product.recommended_supply_30,
                    0,
                  ),
                )}`}
                note={`${PRODUCTION_PLANNING_DAYS} дней`}
              />
              <CompactFact
                label="Артикулы в риске"
                value={formatNumber(
                  products.filter((product) => product.risk_level !== "ok")
                    .length,
                )}
                note="риск или критично"
              />
              <CompactFact
                label="Чистый эффект"
                value={formatMoney(
                  products.reduce(
                    (acc, product) => acc + product.expected_net_effect,
                    0,
                  ),
                )}
                note="ожидаемый эффект"
              />
            </div>
            <ProductMiniTable products={products.slice(0, 10)} compact />
          </TabsContent>

          <TabsContent value="acceptance" className="m-0 space-y-3 px-4 pb-4">
            <div className="grid grid-cols-2 gap-3">
              <CompactFact
                label="Статус"
                value={acceptanceLabel(row.acceptance_status)}
                note={
                  row.acceptance_next_available_at
                    ? `${formatDate(row.acceptance_next_available_at)} · k=${row.acceptance_coefficient ?? "—"}`
                    : `k=${row.acceptance_coefficient ?? "—"}`
                }
              />
              <CompactFact
                label="Разгрузка"
                value={row.allow_unload === false ? "нет" : "да"}
                note={
                  row.acceptance_box_type_id
                    ? `тип короба ${row.acceptance_box_type_id}`
                    : `${row.box_type_ids.length || 0} типов коробов`
                }
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
            </div>
            <div className="flex flex-wrap gap-1.5">
              {row.box_type_ids.length ? (
                row.box_type_ids.map((id) => (
                  <Badge key={id} variant="outline">
                    тип короба {id}
                  </Badge>
                ))
              ) : (
                <Badge variant="outline">тип короба —</Badge>
              )}
            </div>
          </TabsContent>

          <TabsContent value="plan" className="m-0 space-y-3 px-4 pb-4">
            <Alert className={severityClass(row.risk_level)}>
              <Gauge className="h-4 w-4" />
              <AlertTitle>{calc.priority}</AlertTitle>
              <AlertDescription className="mt-1 text-sm">
                {row.recommendation ||
                  "Склад держит нормальный запас и цену логистики."}
              </AlertDescription>
            </Alert>
            <div className="grid grid-cols-2 gap-3">
              <CompactFact
                label="Открытые поставки"
                value={formatNumber(row.open_supply_count)}
                note={`${formatNumber(row.supply_count)} всего`}
              />
              <CompactFact
                label="Нужно докинуть"
                value={`+${formatNumber(calc.replenishmentQty)}`}
                note={`${FAST_REPLENISHMENT_DAYS} дн. покрытие`}
              />
              <CompactFact
                label="Спрос региона"
                value={`${formatNumber(row.region_sales_qty)} шт`}
                note={formatMoney(row.region_sales_amount)}
              />
              <CompactFact
                label="Доля региона"
                value={formatPercent(row.region_sales_share_percent)}
                note="спрос региона"
              />
            </div>
            {relatedSupplies.length > 0 && (
              <div className="space-y-2">
                {relatedSupplies.map((supply) => (
                  <div
                    key={supply.supply_id}
                    className="grid grid-cols-[1fr_auto] gap-3 border-t pt-2 text-sm"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-medium">
                        #{supply.supply_id} · {supply.status_label}
                      </div>
                      <div className="truncate text-xs text-muted-foreground">
                        {formatDateTime(supply.supply_date)}
                      </div>
                    </div>
                    <div className="text-right text-xs">
                      <div className="font-medium">
                        {formatNumber(supply.accepted_qty)}/
                        {formatNumber(supply.planned_qty)}
                      </div>
                      <div
                        className={cn(
                          "text-muted-foreground",
                          supply.gap_qty > 0 && "text-destructive",
                        )}
                      >
                        разница {formatNumber(supply.gap_qty)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <Button asChild size="sm" className="w-full gap-2">
              <Link to="/stock-control">
                <PackagePlus className="h-4 w-4" />
                План поставки
                <ArrowUpRight className="h-4 w-4" />
              </Link>
            </Button>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
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
                    WB {product.nm_id ?? "—"} · {product.brand || "—"}
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
                  label="Чистый эффект"
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
      <div className="hidden overflow-x-auto sm:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-[190px]">Артикул</TableHead>
              <TableHead>Риск</TableHead>
              <TableHead className="text-right">Остаток</TableHead>
              <TableHead className="text-right">Продажи</TableHead>
              <TableHead className="text-right">30 дн.</TableHead>
              {!compact && (
                <TableHead className="text-right">Чистый эффект</TableHead>
              )}
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
                      WB {product.nm_id ?? "—"} · {product.brand || "—"}
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
                  <div className="font-medium">
                    {formatNumber(product.sales_qty)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {formatNumber(product.avg_daily_sales)} / день
                  </div>
                </TableCell>
                <TableCell className="text-right font-medium">
                  +{formatNumber(product.recommended_supply_30)}
                </TableCell>
                {!compact && (
                  <TableCell className="text-right">
                    <div className="font-medium">
                      {formatMoney(product.expected_net_effect)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {formatMoney(product.potential_revenue)}
                    </div>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="divide-y sm:hidden">
        {products.map((product) => (
          <div key={product.id} className="grid gap-2 px-3 py-3 text-sm">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate font-medium">
                  {productLabel(product)}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  WB {product.nm_id ?? "—"} · {product.warehouse_name}
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
                label="Чистый эффект"
                value={formatMoney(product.expected_net_effect)}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FormulaLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/20 px-3 py-2">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 break-words font-mono text-xs">{value}</div>
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

function LogisticsDetailsWorkspace({
  paidStorage,
  acceptance,
  transit,
  sellerWarehouses,
  onExport,
  exportingDataset,
}: {
  paidStorage: PaidStorageDetailRow[];
  acceptance: AcceptanceDetailRow[];
  transit: TransitTariffRow[];
  sellerWarehouses: SellerWarehouseRow[];
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
    <div className="space-y-3">
      <Card className="rounded-lg">
        <CardContent className="grid gap-0 p-0 sm:grid-cols-2 xl:grid-cols-4 xl:divide-x">
          <DetailStat
            label="Хранение по SKU"
            value={formatMoney(storageTotal)}
            icon={Layers3}
          />
          <DetailStat
            label="Приёмка по операциям"
            value={formatMoney(acceptanceTotal)}
            icon={PackageCheck}
          />
          <DetailStat
            label="Транзитных маршрутов"
            value={formatNumber(transit.length)}
            icon={RouteIcon}
          />
          <DetailStat
            label="Остаток FBS/DBW"
            value={formatNumber(sellerStockTotal)}
            icon={Warehouse}
          />
        </CardContent>
      </Card>

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
          <div className="text-right">
            <div className="font-semibold">
              {formatMoney(row.original.amount)}
            </div>
            <div className="text-xs text-muted-foreground">
              {formatPercent(row.original.share_percent)}
            </div>
          </div>
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
      emptyText="Запустите sync logistics: он создаст task /api/v1/paid_storage, дождётся статуса done и скачает report."
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
          <div className="text-right">
            <div className="font-semibold">
              {formatMoney(row.original.amount)}
            </div>
            <div className="text-xs text-muted-foreground">
              {formatPercent(row.original.share_percent)}
            </div>
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
          <div className="text-right font-semibold">
            {formatMoney(row.original.amount)}
          </div>
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
        accessorFn: (row) => row.delivery_type_label || "",
        header: ({ column }) => (
          <SortableHeader column={column} label="Модель" />
        ),
        cell: ({ row }) => (
          <Badge variant="outline">
            {row.original.delivery_type_label || "—"}
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
      <Alert>
        <Database className="h-4 w-4" />
        <AlertTitle>{emptyTitle}</AlertTitle>
        <AlertDescription>{emptyText}</AlertDescription>
      </Alert>
    );
  }
  return (
    <Card className="rounded-lg">
      <CardHeader className="border-b pb-3">
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
            Экспорт
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

function detailProductLabel(row: PaidStorageDetailRow | AcceptanceDetailRow) {
  return row.vendor_code || row.title || row.barcode || row.brand || "товар";
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

  if (!rows.length) return <SupplyTable rows={rows} />;

  return (
    <div className="space-y-3">
      <Card className="rounded-lg">
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
      <SupplyTable rows={rows} />
    </div>
  );
}

function SupplyTable({ rows }: { rows: SupplyRow[] }) {
  if (!rows.length) {
    return (
      <Alert>
        <Factory className="h-4 w-4" />
        <AlertTitle>Поставки не найдены</AlertTitle>
        <AlertDescription>
          Список появится после загрузки FBO-поставок и товаров в поставках.
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <Card className="rounded-lg">
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
                    <Badge variant="outline">{row.status_label}</Badge>
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
  );
}

function CapabilityTable({ rows }: { rows: CapabilityRow[] }) {
  return (
    <Card className="rounded-lg">
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Возможность</TableHead>
                <TableHead>Маршрут API</TableHead>
                <TableHead>Категория ключа</TableHead>
                <TableHead>Статус</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.key}>
                  <TableCell>
                    <div className="font-medium">{row.label}</div>
                    {row.note && (
                      <div className="text-xs text-muted-foreground">
                        {row.note}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="max-w-[520px] truncate font-mono text-xs">
                    {row.endpoint}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{row.token_category}</Badge>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={row.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
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

function PriorityBadge({ priority }: { priority: string }) {
  const meta = {
    recommended: [
      "Рекомендовано",
      "border-emerald-200 bg-emerald-50 text-emerald-700",
    ],
    planned: ["Планово", "border-blue-200 bg-blue-50 text-blue-700"],
    blocked: ["Слот закрыт", "border-red-200 bg-red-50 text-red-700"],
  }[priority] || [priority, "border-slate-200 bg-slate-50 text-slate-600"];
  return (
    <Badge variant="outline" className={meta[1]}>
      {meta[0]}
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
  }[mode] || [mode, "border-slate-200 bg-slate-50 text-slate-600"];
  return (
    <Badge variant="outline" className={meta[1]}>
      {meta[0]}
    </Badge>
  );
}

function confidenceLabel(value: string) {
  if (value === "high") return "высокая точность";
  if (value === "low") return "мало данных";
  return "средняя точность";
}

function taskTypeLabel(value: string) {
  return (
    {
      stockout: "дефицит",
      low_stock: "мало остатка",
      logistics_cost: "дорогая логистика",
      buyout_drop: "низкий выкуп",
      acceptance: "приёмка",
      regional_supply: "региональная поставка",
    }[value] || value.replaceAll("_", " ")
  );
}

function buyoutReasonCopy(tag: string) {
  const normalized = tag.toLowerCase();
  if (normalized.includes("oos")) {
    return "Товар исчезает из региональной выдачи, скорость доставки и видимость падают.";
  }
  if (normalized.includes("доставка") || normalized.includes("лог")) {
    return "Длинное или дорогое плечо доставки снижает привлекательность оффера.";
  }
  if (normalized.includes("цена")) {
    return "Цена могла стать хуже конкурентов, покупатель чаще отказывается.";
  }
  if (normalized.includes("отзы")) {
    return "Негативные отзывы или низкая оценка портят первое впечатление.";
  }
  if (normalized.includes("отмен")) {
    return "Отмены и возвраты искажают выкуп и сигнализируют о проблеме поставки.";
  }
  return "Фактор стоит проверить в карточке, остатках и финансовой аналитике.";
}

function reasonDotClass(tag: string) {
  const normalized = tag.toLowerCase();
  if (normalized.includes("oos") || normalized.includes("отмен"))
    return "bg-red-500";
  if (normalized.includes("цена") || normalized.includes("лог"))
    return "bg-orange-500";
  if (normalized.includes("отзы")) return "bg-pink-500";
  return "bg-slate-400";
}

function relatedProductsForTask(
  products: ProductRow[],
  task: LogisticsTaskRow,
) {
  const related = products.filter((product) => {
    if (task.warehouse_name) {
      return product.warehouse_name === task.warehouse_name;
    }
    if (task.region_name) {
      return product.region_name === task.region_name;
    }
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

function riskWeight(level: string) {
  if (level === "danger") return 0;
  if (level === "warning") return 1;
  if (level === "watch") return 2;
  return 3;
}

function productLabel(product: ProductRow) {
  return (
    product.vendor_code ||
    product.title ||
    product.barcode ||
    (product.nm_id ? String(product.nm_id) : "артикул")
  );
}

function compactProduct(name: string) {
  if (!name) return "—";
  return name.length > 15 ? `${name.slice(0, 14)}…` : name;
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

function priorityLabel(row: WarehouseRow) {
  if (row.risk_level === "danger") return "Срочно";
  if (row.risk_level === "warning") return "Сегодня";
  if (row.risk_level === "watch") return "Контроль";
  return "Планово";
}

function acceptanceLabel(status: string) {
  return (
    {
      available: "доступно",
      expensive: "дорого",
      closed: "закрыто",
      unknown: "нет данных",
    }[status] || status
  );
}

function RiskBadge({ level }: { level: string }) {
  const label =
    {
      danger: "Критично",
      warning: "Риск",
      watch: "Наблюдать",
      ok: "ОК",
    }[level] || level;
  return <Badge className={riskClass(level)}>{label}</Badge>;
}

function StatusBadge({ status }: { status: string }) {
  const meta = {
    ok: ["ОК", "border-emerald-200 bg-emerald-50 text-emerald-700"],
    active: ["Активно", "border-emerald-200 bg-emerald-50 text-emerald-700"],
    available: [
      "Доступно",
      "border-emerald-200 bg-emerald-50 text-emerald-700",
    ],
    planned: ["В плане", "border-amber-200 bg-amber-50 text-amber-700"],
    expensive: ["Дорого", "border-amber-200 bg-amber-50 text-amber-700"],
    stale: ["Устарело", "border-amber-200 bg-amber-50 text-amber-700"],
    closed: ["Закрыто", "border-red-200 bg-red-50 text-red-700"],
    empty: ["Нет данных", "border-slate-200 bg-slate-50 text-slate-600"],
    missing: ["Нет данных", "border-slate-200 bg-slate-50 text-slate-600"],
    unknown: ["Неизвестно", "border-slate-200 bg-slate-50 text-slate-600"],
  }[status] || [status, "border-slate-200 bg-slate-50 text-slate-600"];
  return (
    <Badge variant="outline" className={meta[1]}>
      {meta[0]}
    </Badge>
  );
}

function compactWarehouse(name: string) {
  if (!name) return "—";
  return name.length > 13 ? `${name.slice(0, 12)}.` : name;
}

function riskClass(level: string) {
  if (level === "danger") return "bg-red-600 text-white hover:bg-red-600";
  if (level === "warning")
    return "bg-orange-500 text-white hover:bg-orange-500";
  if (level === "watch")
    return "bg-amber-100 text-amber-800 hover:bg-amber-100";
  return "bg-emerald-100 text-emerald-800 hover:bg-emerald-100";
}

function riskDotClass(level: string) {
  if (level === "danger") return "bg-red-500";
  if (level === "warning") return "bg-orange-500";
  if (level === "watch") return "bg-amber-400";
  return "bg-emerald-500";
}

function severityClass(level: string) {
  if (level === "danger") return "border-red-200 bg-red-50 text-red-900";
  if (level === "warning")
    return "border-orange-200 bg-orange-50 text-orange-900";
  if (level === "ok")
    return "border-emerald-200 bg-emerald-50 text-emerald-900";
  return "border-amber-200 bg-amber-50 text-amber-900";
}
