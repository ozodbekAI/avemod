// @ts-nocheck
// /stock-control — Остатки и регионы (Stock Control + Regional Supply).
// Etap 1: Canonical navigation + Overview tab + tab shell.
// Frontend always talks to Finance backend (no direct StockOps calls).
import { createFileRoute, Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { useAccounts } from "@/lib/account-context";
import { useModuleStatus } from "@/lib/modules-health";
import { PageShell, PageHeader } from "@/components/PageShell";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { EndpointError } from "@/components/EndpointError";
import { ReturnWizard } from "@/components/stock-control/ReturnWizard";
import { RegionalSupplyWizard } from "@/components/stock-control/RegionalSupplyWizard";
import { StoreBalanceWizard } from "@/components/stock-control/StoreBalanceWizard";
import { HistoryTab } from "@/components/stock-control/HistoryTab";
import { SettingsTab } from "@/components/stock-control/SettingsTab";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { formatNumber, formatMoney, formatDateTime } from "@/lib/format";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { ActionCenterReturnLink } from "@/components/action-center/ActionCenterReturnLink";
import {
  Boxes, AlertTriangle, PackageX, Snowflake, MapPin, Clock,
  PackagePlus, Undo2, Wrench, Database,
} from "lucide-react";
import { z } from "zod";

const tabSchema = z.object({
  tab: z.enum(["overview", "return", "supply", "balance", "history", "settings"]).optional(),
  problem_instance_id: z.preprocess(
    (value) => (value === null || value === undefined ? undefined : String(value)),
    z.string().optional(),
  ),
  nm_id: z.preprocess(
    (value) => (value === null || value === undefined ? undefined : String(value)),
    z.string().optional(),
  ),
});

export const Route = createFileRoute("/_authenticated/stock-control")({
  validateSearch: tabSchema,
  component: StockControlPage,
  errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} />,
});

// ─── Types (loose — backend shape may evolve) ────────────────────────
type OverviewKpis = {
  total_stock_units?: number | null;
  total_stock_value?: number | null;
  shortage_products_count?: number | null;
  excess_products_count?: number | null;
  frozen_units?: number | null;
  frozen_value?: number | null;
  regions_with_shortage?: number | null;
  regions_with_excess?: number | null;
  warehouse_mapping_coverage_percent?: number | null;
  unmapped_warehouses?: number | null;
  latest_successful_run_id?: number | string | null;
  latest_successful_run_at?: string | null;
  source_freshness?: {
    stock_snapshot_at?: string | null;
    regional_demand_at?: string | null;
    [k: string]: any;
  } | null;
};
type OverviewResponse = {
  kpis?: OverviewKpis;
  status?: string | null;
  message?: string | null;
  warnings?: string[];
  [k: string]: any;
};

function StockControlPage() {
  const { activeId } = useAccounts();
  const navigate = useNavigate();
  const search = Route.useSearch();
  const tab = search.tab ?? "overview";
  const setTab = (t: string) =>
    navigate({
      to: "/stock-control",
      search: {
        tab: t as any,
        ...(search.problem_instance_id ? { problem_instance_id: search.problem_instance_id } : {}),
        ...(search.nm_id ? { nm_id: search.nm_id } : {}),
      },
      replace: true,
    });

  const moduleStatus = useModuleStatus("stockops");

  return (
    <PageShell>
      <PageHeader
        title="Остатки и регионы"
        description="Управление остатками: возврат лишнего, распределение поставок по регионам, баланс магазинов."
        actions={
          moduleStatus.status && (
            <ModuleStatusBadge status={moduleStatus.status} beta={moduleStatus.beta} />
          )
        }
      />

      <ActionCenterReturnLink
        problem_instance_id={search.problem_instance_id}
        nm_id={search.nm_id}
        className="mb-4"
      />

      {!activeId && <NoAccountSelected />}

      {activeId && <DataDependencyNotice accountId={activeId} domains={["stocks", "sales", "orders", "finance", "product_cards", "supplies"]} />}

      {activeId && (
        <Tabs value={tab} onValueChange={setTab} className="w-full">
          <TabsList className="flex flex-wrap h-auto">
            <TabsTrigger value="overview" className="text-xs">Обзор</TabsTrigger>
            <TabsTrigger value="return" className="text-xs">Возврат лишнего</TabsTrigger>
            <TabsTrigger value="supply" className="text-xs">Поставка по регионам</TabsTrigger>
            <TabsTrigger value="balance" className="text-xs">Баланс магазинов</TabsTrigger>
            <TabsTrigger value="history" className="text-xs">История расчётов</TabsTrigger>
            <TabsTrigger value="settings" className="text-xs">Параметры</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="mt-4">
            <OverviewTab accountId={activeId} setTab={setTab} />
          </TabsContent>
          <TabsContent value="return" className="mt-4">
            <ReturnWizard accountId={activeId} />
          </TabsContent>
          <TabsContent value="supply" className="mt-4">
            <RegionalSupplyWizard accountId={activeId} />
          </TabsContent>
          <TabsContent value="balance" className="mt-4">
            <StoreBalanceWizard accountId={activeId} />
          </TabsContent>
          <TabsContent value="history" className="mt-4">
            <HistoryTab accountId={activeId} />
          </TabsContent>
          <TabsContent value="settings" className="mt-4">
            <SettingsTab accountId={activeId} />
          </TabsContent>
        </Tabs>
      )}
    </PageShell>
  );
}

function ModuleStatusBadge({ status, beta }: { status: string; beta?: boolean }) {
  const key = status.toLowerCase();
  const map: Record<string, { label: string; cls: string }> = {
    ok:             { label: "Подключен",     cls: "bg-success/10 text-success border-success/30" },
    empty:          { label: "Нет данных",    cls: "bg-muted text-muted-foreground border-border" },
    not_configured: { label: "Не настроен",   cls: "bg-muted text-muted-foreground border-border" },
    disabled:       { label: "Отключен",      cls: "bg-muted text-muted-foreground border-border" },
    unavailable:    { label: "Недоступен",    cls: "bg-destructive/10 text-destructive border-destructive/30" },
    error:          { label: "Ошибка",        cls: "bg-destructive/10 text-destructive border-destructive/30" },
    warning:        { label: "Внимание",      cls: "bg-warning/10 text-warning border-warning/30" },
  };
  const meta = map[key] ?? map.ok;
  return (
    <div className="flex items-center gap-2">
      <Badge variant="outline" className={meta.cls}>{meta.label}</Badge>
      {beta && <Badge variant="outline" className="bg-primary/10 text-primary border-primary/30">Beta</Badge>}
    </div>
  );
}

// ─── Overview tab ─────────────────────────────────────────────────────
function OverviewTab({ accountId, setTab }: { accountId: number; setTab: (t: string) => void }) {
  const q = useQuery({
    queryKey: ["stock-control-overview", accountId],
    queryFn: () =>
      api<OverviewResponse>(API_ENDPOINTS.portal.stockControlOverview, {
        query: { account_id: accountId },
      }),
    staleTime: 60_000,
    retry: false,
  });

  if (q.isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-20" />)}
        </div>
        <Skeleton className="h-24" />
      </div>
    );
  }

  if (q.isError) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Не удалось загрузить обзор</AlertTitle>
        <AlertDescription className="space-y-2">
          <div>{(q.error as Error).message}</div>
          <Button size="sm" variant="outline" onClick={() => q.refetch()}>Повторить</Button>
        </AlertDescription>
      </Alert>
    );
  }

  const data = q.data ?? {};
  const k: OverviewKpis = data.kpis ?? (data as any);
  const fresh = k.source_freshness ?? null;

  const hasAny =
    k.total_stock_units != null || k.total_stock_value != null ||
    k.shortage_products_count != null || k.excess_products_count != null;

  return (
    <div className="space-y-4">
      {/* CTA row */}
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => setTab("return")} className="gap-2">
          <Undo2 className="h-4 w-4" />
          Рассчитать возврат лишнего
        </Button>
        <Button onClick={() => setTab("supply")} variant="default" className="gap-2">
          <PackagePlus className="h-4 w-4" />
          Распределить новую поставку
        </Button>
        <Button onClick={() => setTab("settings")} variant="outline" className="gap-2">
          <Wrench className="h-4 w-4" />
          Параметры
        </Button>
      </div>

      {/* Warnings */}
      {Array.isArray(data.warnings) && data.warnings.length > 0 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Предупреждения</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5 text-sm space-y-0.5">
              {data.warnings.map((w, i) => <li key={i}>{humanizeWarning(w)}</li>)}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {!hasAny && !q.isFetching && (
        <Alert>
          <AlertTitle>Пока нет данных</AlertTitle>
          <AlertDescription>
            Запустите первый расчёт — возврат лишнего или распределение поставки — чтобы увидеть сводку.
          </AlertDescription>
        </Alert>
      )}

      {/* KPI grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiTile
          icon={<Boxes className="h-4 w-4" />}
          label="Всего на складах"
          value={k.total_stock_units != null ? formatNumber(k.total_stock_units) : "—"}
          hint="единиц"
        />
        <KpiTile
          icon={<Database className="h-4 w-4" />}
          label="Стоимость остатков"
          value={k.total_stock_value != null ? formatMoney(k.total_stock_value) : "—"}
        />
        <KpiTile
          icon={<AlertTriangle className="h-4 w-4 text-warning" />}
          label="Товары в дефиците"
          value={k.shortage_products_count != null ? formatNumber(k.shortage_products_count) : "—"}
          tone={k.shortage_products_count && k.shortage_products_count > 0 ? "warning" : "default"}
        />
        <KpiTile
          icon={<PackageX className="h-4 w-4 text-destructive" />}
          label="Товары в излишке"
          value={k.excess_products_count != null ? formatNumber(k.excess_products_count) : "—"}
          tone={k.excess_products_count && k.excess_products_count > 0 ? "danger" : "default"}
        />
        <KpiTile
          icon={<Snowflake className="h-4 w-4 text-primary" />}
          label="Замороженный товар"
          value={k.frozen_units != null ? formatNumber(k.frozen_units) : "—"}
          hint={k.frozen_value != null ? formatMoney(k.frozen_value) : undefined}
        />
        <KpiTile
          icon={<MapPin className="h-4 w-4 text-warning" />}
          label="Регионы с дефицитом"
          value={k.regions_with_shortage != null ? formatNumber(k.regions_with_shortage) : "—"}
        />
        <KpiTile
          icon={<MapPin className="h-4 w-4 text-destructive" />}
          label="Регионы с излишком"
          value={k.regions_with_excess != null ? formatNumber(k.regions_with_excess) : "—"}
        />
        <KpiTile
          icon={<Database className="h-4 w-4" />}
          label="Покрытие сопоставления складов"
          value={k.warehouse_mapping_coverage_percent != null
            ? `${Math.round(k.warehouse_mapping_coverage_percent)}%`
            : "—"}
          hint={k.unmapped_warehouses != null && k.unmapped_warehouses > 0
            ? `${k.unmapped_warehouses} не сопоставлено`
            : undefined}
          tone={k.unmapped_warehouses && k.unmapped_warehouses > 0 ? "warning" : "default"}
        />
      </div>

      {/* Freshness footer */}
      <Card>
        <CardContent className="p-4 space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Свежесть данных
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <FreshRow
              label="Снимок остатков"
              value={fresh?.stock_snapshot_at}
            />
            <FreshRow
              label="Региональный спрос"
              value={fresh?.regional_demand_at}
            />
            <FreshRow
              label="Последний успешный расчёт"
              value={k.latest_successful_run_at}
              extra={k.latest_successful_run_id != null
                ? <span className="ml-2 font-mono opacity-60">#{k.latest_successful_run_id}</span>
                : null}
            />
          </div>
          {k.latest_successful_run_id != null && (
            <div className="pt-1">
              <Button asChild variant="ghost" size="sm" className="h-7 text-xs">
                <Link
                  to="/stock-control"
                  search={{ tab: "history" }}
                >
                  Открыть историю расчётов
                </Link>
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function KpiTile({
  icon, label, value, hint, tone = "default",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "warning" | "danger";
}) {
  const toneCls =
    tone === "danger" ? "border-destructive/30"
    : tone === "warning" ? "border-warning/30"
    : "border-border";
  return (
    <Card className={toneCls}>
      <CardContent className="p-3 space-y-1">
        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {icon}
          <span>{label}</span>
        </div>
        <div className="text-xl font-semibold tabular-nums">{value}</div>
        {hint && <div className="text-[11px] text-muted-foreground">{hint}</div>}
      </CardContent>
    </Card>
  );
}

function FreshRow({
  label, value, extra,
}: { label: string; value?: string | null; extra?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <Clock className="h-3 w-3 text-muted-foreground shrink-0" />
      <span className="text-muted-foreground">{label}:</span>
      <span className="font-medium tabular-nums">
        {value ? formatDateTime(value) : "—"}
      </span>
      {extra}
    </div>
  );
}

function PlaceholderTab({ title }: { title: string }) {
  return (
    <Card>
      <CardContent className="p-10 text-center space-y-2">
        <div className="text-base font-medium">{title}</div>
        <div className="text-sm text-muted-foreground">
          Раздел готовится. Уже доступна вкладка «Обзор».
        </div>
      </CardContent>
    </Card>
  );
}

function humanizeWarning(code: string): string {
  const map: Record<string, string> = {
    warehouse_mapping_incomplete: "Не все склады WB сопоставлены с регионами — расчёт может быть неполным.",
    no_regional_demand:           "Региональный спрос ещё не рассчитан.",
    stock_snapshot_stale:         "Снимок остатков устарел — обновите данные.",
    no_successful_run:            "Ещё нет ни одного успешного расчёта.",
  };
  return map[code] ?? code;
}
