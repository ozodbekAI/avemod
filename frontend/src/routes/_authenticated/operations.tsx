// /operations — operational / debug page. NOT the owner money page.
//
// Real endpoints used:
//   GET /api/v1/orders
//   GET /api/v1/sales
//   GET /api/v1/supplies
//   GET /api/v1/sync/runs
//   GET /api/v1/sync/cursors
//   GET /api/v1/dashboard/data-health
//
// Never call GET /api/v1/operations — it does not exist.
//
// Heavy tables (orders/sales/supplies) are lazy-mounted per tab so we never
// fetch them all at once.
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataBrowser, type Column } from "@/components/DataBrowser";
import { fmtDate, fmtMoney, fmtNum, fmtPct } from "@/components/Pager";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { api, apiList, type DashboardDataHealth, type Row, type SyncRun, type SyncCursor } from "@/lib/api";
import { useAccounts } from "@/lib/account-context";
import {
  Play, RefreshCw, Loader2, CheckCircle2, XCircle, AlertCircle, Clock,
  Activity, Info,
} from "lucide-react";
import { EndpointError } from "@/components/EndpointError";

export const Route = createFileRoute("/_authenticated/operations")({
  component: OperationsPage,
  errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} />,
});

const DOMAINS = [
  "products","prices","orders","sales","stocks","finance","ads","analytics","supplies","tariffs","documents",
];

/* ─── helpers ─────────────────────────────────────────────────────────── */

function statusIcon(status?: string | null) {
  const s = (status ?? "").toLowerCase();
  if (s === "success" || s === "ok" || s === "completed") return <CheckCircle2 className="h-4 w-4 text-success" />;
  if (s === "failed" || s === "error") return <XCircle className="h-4 w-4 text-destructive" />;
  if (s === "running" || s === "in_progress") return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  if (!status) return <Clock className="h-4 w-4 text-muted-foreground" />;
  return <AlertCircle className="h-4 w-4 text-warning" />;
}

/* ─── Sync status tab ─────────────────────────────────────────────────── */

function SyncTab() {
  const { activeId } = useAccounts();
  const qc = useQueryClient();
  const enabled = !!activeId;

  const healthQ = useQuery<DashboardDataHealth>({
    queryKey: ["ops-data-health", activeId],
    enabled,
    queryFn: () => api<DashboardDataHealth>("/dashboard/data-health", { query: { account_id: activeId! } }),
    refetchInterval: 15000,
  });

  const runsQ = useQuery({
    queryKey: ["ops-sync-runs", activeId],
    enabled,
    queryFn: () => apiList<SyncRun>("/sync/runs", { query: { account_id: activeId!, limit: 50, offset: 0 } }),
    refetchInterval: 5000,
  });

  const cursorsQ = useQuery({
    queryKey: ["ops-sync-cursors", activeId],
    enabled,
    queryFn: () => apiList<SyncCursor>("/sync/cursors", { query: { account_id: activeId! } }),
    refetchInterval: 15000,
  });

  const [domain, setDomain] = useState("products");
  const [forceFull, setForceFull] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const trigger = useMutation({
    mutationFn: () =>
      api("/sync/trigger", { method: "POST", body: { account_id: activeId, domain, force_full: forceFull } }),
    onSuccess: () => {
      toast.success(`Синхронизация ${domain} запущена`);
      qc.invalidateQueries({ queryKey: ["ops-sync-runs", activeId] });
      qc.invalidateQueries({ queryKey: ["ops-data-health", activeId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const backfill = useMutation({
    mutationFn: () =>
      api("/sync/backfill", {
        method: "POST",
        body: {
          account_id: activeId, domain,
          date_from: dateFrom || null, date_to: dateTo || null,
          force_full: forceFull,
        },
      }),
    onSuccess: () => {
      toast.success(`Перезагрузка ${domain} запущена`);
      qc.invalidateQueries({ queryKey: ["ops-sync-runs", activeId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const domains = healthQ.data?.domains ?? [];
  const failedCount = healthQ.data?.failed_domains?.length ?? 0;
  const missedDays = healthQ.data?.missed_days_count ?? 0;
  const openIssues = healthQ.data?.open_issues_total ?? 0;
  const runningRuns = (runsQ.data ?? []).filter((r) => (r.status ?? "").toLowerCase() === "running").length;

  if (!activeId) return <div className="p-6 text-sm text-muted-foreground">Сначала выберите аккаунт.</div>;

  return (
    <div className="space-y-4">
      {/* Stat bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SyncStat label="Доменов" value={fmtNum(domains.length)} />
        <SyncStat label="Сейчас выполняется" value={fmtNum(runningRuns)} tone={runningRuns > 0 ? "info" : undefined} />
        <SyncStat label="С ошибками" value={fmtNum(failedCount)} tone={failedCount > 0 ? "bad" : "ok"} />
        <SyncStat label="Пропущенных дней" value={fmtNum(missedDays)} tone={missedDays > 0 ? "warn" : "ok"} hint={`Открытых проблем: ${openIssues}`} />
      </div>

      {/* Actions */}
      <div className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Запустить синхронизацию</CardTitle>
            <CardDescription className="text-xs">Дельта-загрузка или backfill по диапазону</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <div>
              <Label className="text-xs">Домен</Label>
              <Select value={domain} onValueChange={setDomain}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{DOMAINS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div><Label className="text-xs">Дата с</Label><Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
              <div><Label className="text-xs">Дата по</Label><Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <Switch checked={forceFull} onCheckedChange={setForceFull} />
              <Label className="text-sm">Полная загрузка</Label>
            </div>
            <div className="flex gap-2 pt-2">
              <Button className="flex-1" disabled={trigger.isPending} onClick={() => trigger.mutate()}>
                <Play className="h-4 w-4 mr-1.5" />Запустить
              </Button>
              <Button variant="outline" className="flex-1" disabled={backfill.isPending} onClick={() => backfill.mutate()}>
                <RefreshCw className="h-4 w-4 mr-1.5" />Backfill
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Состояние данных</CardTitle>
            <CardDescription className="text-xs">Источник: /dashboard/data-health · обновляется каждые 15 сек</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row2 label="Активных SKU" value={fmtNum(healthQ.data?.active_sku_count ?? 0)} />
            <Row2 label="С себестоимостью" value={fmtNum(healthQ.data?.active_sku_with_manual_cost_count ?? 0)} />
            <Row2 label="Покрытие SKU" value={fmtPct(healthQ.data?.sku_cost_coverage_percent)} />
            <Row2 label="Покрытие выручки" value={fmtPct(healthQ.data?.revenue_cost_coverage_percent)} />
            <Row2 label="Без себестоимости" value={fmtNum(healthQ.data?.missing_manual_cost_count ?? 0)}
              tone={(healthQ.data?.missing_manual_cost_count ?? 0) > 0 ? "warn" : undefined} />
            <Row2 label="Пропущенных дней" value={fmtNum(missedDays)} tone={missedDays > 0 ? "warn" : undefined} />
          </CardContent>
        </Card>
      </div>

      {/* Domains status */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Состояние доменов</CardTitle>
          <CardDescription className="text-xs">/dashboard/data-health · обновляется каждые 15 сек</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Домен</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Курсор</TableHead>
                <TableHead>Последний запуск</TableHead>
                <TableHead>Последний успех</TableHead>
                <TableHead>Ошибка</TableHead>
                <TableHead className="text-right">Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {domains.map((d) => (
                <TableRow key={d.domain}>
                  <TableCell className="font-mono text-xs">{d.domain}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      {statusIcon(d.latest_status)}
                      <span className="text-xs">{d.latest_status ?? "—"}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">{d.cursor_status ?? "—"}</TableCell>
                  <TableCell className="text-xs">{fmtDate(d.latest_finished_at)}</TableCell>
                  <TableCell className="text-xs">{fmtDate(d.last_successful_at)}</TableCell>
                  <TableCell className="text-xs text-destructive max-w-[280px] truncate">{d.latest_error_text ?? ""}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost" size="sm" className="h-7 text-xs"
                      disabled={trigger.isPending}
                      onClick={() => { setDomain(d.domain); trigger.mutate(); }}
                    >
                      <Play className="h-3 w-3 mr-1" />Запустить
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {domains.length === 0 && (
                <TableRow><TableCell colSpan={7} className="py-6 text-center text-muted-foreground text-sm">Нет данных</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Recent runs */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Последние запуски</CardTitle>
          <CardDescription className="text-xs">/sync/runs?limit=50 · обновляется каждые 5 сек</CardDescription>
        </CardHeader>
        <CardContent className="p-0 max-h-[420px] overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Домен</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Источник</TableHead>
                <TableHead>Начато</TableHead>
                <TableHead>Завершено</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(runsQ.data ?? []).map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">{r.id}</TableCell>
                  <TableCell className="font-mono text-xs">{r.domain}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      {statusIcon(r.status)}
                      <Badge variant={r.status === "success" ? "outline" : r.status === "failed" ? "destructive" : "secondary"} className="text-[10px]">
                        {r.status}
                      </Badge>
                      {r.is_backfill && <Badge variant="outline" className="ml-1 text-[10px]">Backfill</Badge>}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">{r.trigger}</TableCell>
                  <TableCell className="text-xs">{fmtDate(r.started_at)}</TableCell>
                  <TableCell className="text-xs">{fmtDate(r.finished_at)}</TableCell>
                </TableRow>
              ))}
              {(runsQ.data?.length ?? 0) === 0 && (
                <TableRow><TableCell colSpan={6} className="py-6 text-center text-muted-foreground text-sm">Пока нет запусков</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Cursors */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Курсоры синхронизации</CardTitle>
          <CardDescription className="text-xs">/sync/cursors</CardDescription>
        </CardHeader>
        <CardContent className="p-0 max-h-[360px] overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Домен</TableHead>
                <TableHead>Курсор</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Последний раз</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(cursorsQ.data ?? []).map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-mono text-xs">{c.domain}</TableCell>
                  <TableCell className="text-xs font-mono truncate max-w-[280px]">{c.cursor_key ?? "—"}</TableCell>
                  <TableCell><Badge variant="outline" className="text-[10px]">{c.status ?? "—"}</Badge></TableCell>
                  <TableCell className="text-xs">{fmtDate(c.last_synced_at)}</TableCell>
                </TableRow>
              ))}
              {(cursorsQ.data?.length ?? 0) === 0 && (
                <TableRow><TableCell colSpan={4} className="py-6 text-center text-muted-foreground text-sm">Нет курсоров</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function SyncStat({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "ok" | "warn" | "bad" | "info" }) {
  const toneClass =
    tone === "ok" ? "text-success" :
    tone === "warn" ? "text-warning" :
    tone === "bad" ? "text-destructive" :
    tone === "info" ? "text-primary" : "";
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs text-muted-foreground uppercase tracking-wide">{label}</div>
        <div className={`text-2xl font-semibold tabular-nums mt-1 ${toneClass}`}>{value}</div>
        {hint && <div className="text-xs text-muted-foreground mt-0.5">{hint}</div>}
      </CardContent>
    </Card>
  );
}

function Row2({ label, value, tone }: { label: string; value: string; tone?: "warn" | "bad" }) {
  const toneClass = tone === "bad" ? "text-destructive" : tone === "warn" ? "text-warning" : "";
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className={`tabular-nums font-medium ${toneClass}`}>{value}</span>
    </div>
  );
}

/* ─── Data health tab ─────────────────────────────────────────────────── */

function DataHealthTab() {
  const { activeId } = useAccounts();
  const enabled = !!activeId;

  const healthQ = useQuery<DashboardDataHealth>({
    queryKey: ["ops-data-health-full", activeId],
    enabled,
    queryFn: () => api<DashboardDataHealth>("/dashboard/data-health", { query: { account_id: activeId! } }),
    staleTime: 30_000,
  });

  if (!activeId) return <div className="p-6 text-sm text-muted-foreground">Сначала выберите аккаунт.</div>;
  if (healthQ.isLoading) return <div className="p-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 inline animate-spin mr-2" />Загрузка…</div>;
  if (healthQ.isError) return <div className="p-6 text-sm text-destructive">Ошибка загрузки /dashboard/data-health</div>;
  const h = healthQ.data;
  if (!h) return null;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        <SyncStat label="Активных SKU" value={fmtNum(h.active_sku_count)} />
        <SyncStat label="Покрытие SKU" value={fmtPct(h.sku_cost_coverage_percent)} tone={(h.sku_cost_coverage_percent ?? 0) < 80 ? "warn" : "ok"} />
        <SyncStat label="Покрытие выручки" value={fmtPct(h.revenue_cost_coverage_percent)} tone={(h.revenue_cost_coverage_percent ?? 0) < 80 ? "warn" : "ok"} />
        <SyncStat label="Открытых проблем" value={fmtNum(h.open_issues_total ?? 0)} tone={(h.open_issues_total ?? 0) > 0 ? "bad" : "ok"} />
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Состояние доменов</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Домен</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Последний успех</TableHead>
                <TableHead>Курсор</TableHead>
                <TableHead>Ошибка</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {h.domains.map((d) => (
                <TableRow key={d.domain}>
                  <TableCell className="font-mono text-xs">{d.domain}</TableCell>
                  <TableCell><div className="flex items-center gap-1.5">{statusIcon(d.latest_status)}<span className="text-xs">{d.latest_status ?? "—"}</span></div></TableCell>
                  <TableCell className="text-xs">{fmtDate(d.last_successful_at)}</TableCell>
                  <TableCell className="text-xs">{d.cursor_status ?? "—"}</TableCell>
                  <TableCell className="text-xs text-destructive max-w-[280px] truncate">{d.latest_error_text ?? ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

/* ─── Browser columns ─────────────────────────────────────────────────── */

const orderCols: Column<Row>[] = [
  { header: "Дата", sortKey: "date", cell: (r) => <span className="text-xs">{fmtDate((r.date as string | null) ?? (r.created_at as string | null))}</span> },
  { header: "ID операции", sortKey: "srid", cell: (r) => <span className="font-mono text-xs truncate max-w-[120px] block">{(r.srid as string) ?? "—"}</span> },
  { header: "nm_id", sortKey: "nm_id", cell: (r) => <span className="font-mono text-xs">{(r.nm_id as number) ?? "—"}</span> },
  { header: "Артикул", sortKey: "vendor_code", cell: (r) => <span className="text-xs">{(r.vendor_code as string) ?? "—"}</span> },
  { header: "Цена", sortKey: "total_price", align: "right", cell: (r) => fmtMoney((r.total_price as number) ?? (r.price_with_disc as number) ?? (r.finished_price as number)) },
  { header: "Склад", sortKey: "warehouse_name", cell: (r) => <span className="text-xs">{(r.warehouse_name as string) ?? "—"}</span> },
  { header: "Регион", sortKey: "region_name", cell: (r) => <span className="text-xs">{(r.region_name as string) ?? "—"}</span> },
  { header: "Статус", sortKey: "is_cancel", cell: (r) => <Badge variant={r.is_cancel ? "destructive" : "outline"}>{r.is_cancel ? "Отменён" : (r.status as string) ?? "OK"}</Badge> },
];

const saleCols: Column<Row>[] = [
  { header: "Дата", sortKey: "date", cell: (r) => <span className="text-xs">{fmtDate((r.date as string | null) ?? (r.created_at as string | null))}</span> },
  { header: "ID операции", sortKey: "srid", cell: (r) => <span className="font-mono text-xs truncate max-w-[120px] block">{(r.srid as string) ?? "—"}</span> },
  { header: "nm_id", sortKey: "nm_id", cell: (r) => <span className="font-mono text-xs">{(r.nm_id as number) ?? "—"}</span> },
  { header: "Артикул", sortKey: "vendor_code", cell: (r) => <span className="text-xs">{(r.vendor_code as string) ?? "—"}</span> },
  { header: "Цена", sortKey: "price_with_disc", align: "right", cell: (r) => fmtMoney((r.price_with_disc as number) ?? (r.total_price as number)) },
  { header: "К перечислению", sortKey: "for_pay", align: "right", cell: (r) => fmtMoney(r.for_pay as number) },
  { header: "Возврат", sortKey: "is_cancel", cell: (r) => <Badge variant={r.is_cancel ? "destructive" : "outline"}>{r.is_cancel ? "Возврат/отмена" : "Продажа"}</Badge> },
  { header: "Склад", sortKey: "warehouse_name", cell: (r) => <span className="text-xs">{(r.warehouse_name as string) ?? "—"}</span> },
];

const supplyCols: Column<Row>[] = [
  { header: "ID", sortKey: "supply_id", cell: (r) => <span className="font-mono text-xs">{(r.supply_id as string) ?? (r.id as number)}</span> },
  { header: "Склад", sortKey: "warehouse_name", cell: (r) => <span className="text-xs">{(r.warehouse_name as string) ?? "—"}</span> },
  { header: "Статус", sortKey: "status_id", cell: (r) => <Badge variant="outline">{(r.status_name as string) ?? (r.status_id as number)?.toString() ?? "—"}</Badge> },
  { header: "Создан", sortKey: "created_at", cell: (r) => <span className="text-xs">{fmtDate((r.created_at as string | null) ?? (r.date as string | null))}</span> },
];

const orderFilters = [
  { key: "srid", label: "ID операции", type: "text" as const },
  { key: "order_id", label: "order_id", type: "text" as const },
  { key: "vendor_code", label: "Артикул", type: "text" as const },
  { key: "barcode", label: "Штрихкод", type: "text" as const },
  { key: "warehouse_name", label: "Склад", type: "text" as const },
  { key: "region_name", label: "Регион", type: "text" as const },
  { key: "is_cancel", label: "Отменённые", type: "bool" as const },
];

/* ─── page ────────────────────────────────────────────────────────────── */

function OperationsPage() {
  const [tab, setTab] = useState("sync");

  return (
    <PageShell>
      <PageHeader
        title="Операции · отладка"
        description="Журналы Wildberries и синхронизация. Это не главная финансовая страница владельца — для бизнеса смотрите /dashboard и /money."
      />

      <Alert className="mb-3">
        <Info className="h-4 w-4" />
        <AlertTitle className="text-sm">Операционная страница</AlertTitle>
        <AlertDescription className="text-xs">
          Тяжёлые таблицы (заказы, продажи, поставки) загружаются только при открытии своей вкладки.
        </AlertDescription>
      </Alert>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex flex-wrap h-auto">
          <TabsTrigger value="sync"><Activity className="h-3.5 w-3.5 mr-1.5" />Синхронизация</TabsTrigger>
          <TabsTrigger value="orders">Заказы</TabsTrigger>
          <TabsTrigger value="sales">Продажи / возвраты</TabsTrigger>
          <TabsTrigger value="supplies">Поставки</TabsTrigger>
          <TabsTrigger value="health">Данные</TabsTrigger>
        </TabsList>

        {/* Lazy-mount: render content only when its tab is active to avoid
            fetching all heavy tables at once. */}
        <TabsContent value="sync">
          {tab === "sync" && <SyncTab />}
        </TabsContent>
        <TabsContent value="orders">
          {tab === "orders" && (
            <DataBrowser path="/orders" columns={orderCols} withDateRange withNmId withSearch extraFilters={orderFilters} queryKey="orders" />
          )}
        </TabsContent>
        <TabsContent value="sales">
          {tab === "sales" && (
            <DataBrowser
              path="/sales" columns={saleCols} withDateRange withNmId withSearch
              extraFilters={[
                { key: "srid", label: "ID операции", type: "text" },
                { key: "sale_id", label: "sale_id", type: "text" },
                { key: "order_id", label: "order_id", type: "text" },
                { key: "vendor_code", label: "Артикул", type: "text" },
                { key: "barcode", label: "Штрихкод", type: "text" },
                { key: "brand", label: "Бренд", type: "text" },
                { key: "subject", label: "Категория", type: "text" },
                { key: "warehouse_name", label: "Склад", type: "text" },
                { key: "is_cancel", label: "Возвраты / отмены", type: "bool" },
              ]}
              queryKey="sales"
            />
          )}
        </TabsContent>
        <TabsContent value="supplies">
          {tab === "supplies" && (
            <DataBrowser
              path="/supplies" columns={supplyCols} withDateRange withSearch
              extraFilters={[
                { key: "supply_id", label: "supply_id", type: "text" },
                { key: "warehouse_name", label: "Склад", type: "text" },
                { key: "status_id", label: "status_id", type: "number" },
              ]}
              queryKey="supplies"
            />
          )}
        </TabsContent>
        <TabsContent value="health">
          {tab === "health" && <DataHealthTab />}
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}
