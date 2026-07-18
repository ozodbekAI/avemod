// Финансовое покрытие данных — 8 источников, от которых зависит расчёт денег.
// Не выдумывает источники и не подменяет отсутствие данных нулём.
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Clock, AlertTriangle, ShieldAlert, PowerOff } from "lucide-react";
import {
  fetchDataSyncStatus,
  type DataSyncDomainStatus,
} from "@/components/data-health/DataCoveragePanel";
import { formatDateTime } from "@/lib/format";

type Tone = "ok" | "fresh" | "stale" | "missing" | "not_configured";

const TONE_CLASS: Record<Tone, string> = {
  ok:             "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  fresh:          "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  stale:          "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  missing:        "border-destructive/30 bg-destructive/10 text-destructive",
  not_configured: "border-muted-foreground/30 bg-muted text-muted-foreground",
};

const TONE_LABEL: Record<Tone, string> = {
  ok:             "Подключено",
  fresh:          "Свежие данные",
  stale:          "Устарело",
  missing:        "Не хватает данных",
  not_configured: "Не настроено",
};

const TONE_ICON = {
  ok: CheckCircle2,
  fresh: CheckCircle2,
  stale: Clock,
  missing: AlertTriangle,
  not_configured: PowerOff,
} as const;

function domainTone(d?: DataSyncDomainStatus | null): Tone {
  if (!d) return "not_configured";
  const configured = d.configured ?? d.token_configured;
  if (configured === false) return "not_configured";
  const fresh = String(d.freshness_status ?? "").toLowerCase();
  if (fresh === "fresh") return "fresh";
  if (fresh === "stale") return "stale";
  if (fresh === "missing" || fresh === "failed") return "missing";
  const status = String(d.status ?? "").toLowerCase();
  if (status === "ok" || status === "healthy") return "ok";
  return "missing";
}

interface SourceRow {
  key: string;
  title: string;
  dependsOn: string;
  action?: { label: string; href: string };
  tone?: Tone;
  lastSync?: string | null;
  reason?: string | null;
}

export interface FinanceSourceCoveragePanelProps {
  accountId: number | null;
  costPriceCoverage?: number | null;
  unallocatedExpenses?: number | null;
  onRefresh?: () => void;
}

export function FinanceSourceCoveragePanel({
  accountId,
  costPriceCoverage,
  unallocatedExpenses,
}: FinanceSourceCoveragePanelProps) {
  const q = useQuery({
    queryKey: ["finance-source-coverage", accountId],
    enabled: !!accountId,
    queryFn: () => fetchDataSyncStatus(accountId as number),
    staleTime: 60_000,
  });

  const byDomain = new Map<string, DataSyncDomainStatus>();
  for (const d of q.data?.domains ?? []) byDomain.set(d.domain, d);

  const salesD = byDomain.get("sales");
  const ordersD = byDomain.get("orders");
  const salesOrders = salesD ?? ordersD;
  const salesTone: Tone = (() => {
    const t1 = salesD ? domainTone(salesD) : null;
    const t2 = ordersD ? domainTone(ordersD) : null;
    const order: Tone[] = ["missing", "stale", "not_configured", "ok", "fresh"];
    for (const t of order) if (t1 === t || t2 === t) return t;
    return t1 ?? t2 ?? "not_configured";
  })();

  // Себестоимость — производный «источник» от summary.supplier_coverage_percent.
  const costTone: Tone =
    costPriceCoverage == null ? "missing" :
    costPriceCoverage >= 95 ? "fresh" :
    costPriceCoverage >= 80 ? "ok" :
    costPriceCoverage >= 40 ? "stale" : "missing";
  const costReason =
    costPriceCoverage == null
      ? "Себестоимость не загружена"
      : `Покрытие себестоимости: ${costPriceCoverage.toFixed(0)}%`;

  // Расходы — производный «источник» от summary.unallocated_expenses.
  const expenseTone: Tone =
    unallocatedExpenses == null ? "missing" :
    unallocatedExpenses === 0 ? "fresh" :
    unallocatedExpenses > 0 ? "stale" : "ok";
  const expenseReason =
    unallocatedExpenses == null
      ? "Нет данных о нераспределённых расходах"
      : unallocatedExpenses > 0
        ? "Есть нераспределённые расходы"
        : "Расходы классифицированы";

  const rows: SourceRow[] = [
    {
      key: "finance",
      title: "Финансовые отчёты WB",
      dependsOn: "Подтверждённая выручка, чистая прибыль, баланс WB.",
      tone: byDomain.get("finance") ? domainTone(byDomain.get("finance")) : "not_configured",
      lastSync: byDomain.get("finance")?.last_successful_sync_at ?? byDomain.get("finance")?.last_synced_at ?? null,
      action: { label: "Синхронизировать", href: "/settings" },
    },
    {
      key: "sales_orders",
      title: "Продажи / заказы",
      dependsOn: "Операционная выручка, конверсия, экономика по товарам.",
      tone: salesOrders ? salesTone : "not_configured",
      lastSync: salesOrders?.last_successful_sync_at ?? salesOrders?.last_synced_at ?? null,
      action: { label: "Синхронизировать", href: "/settings" },
    },
    {
      key: "cost_price",
      title: "Себестоимость",
      dependsOn: "Маржа, прибыль на единицу, стоимость остатка.",
      tone: costTone,
      reason: costReason,
      action: { label: "Загрузить себестоимость", href: "/data-fix?tab=cost" },
    },
    {
      key: "expenses",
      title: "Расходы",
      dependsOn: "Прибыль владельца, нераспределённые статьи.",
      tone: expenseTone,
      reason: expenseReason,
      action: { label: "Классифицировать расход", href: "/expenses" },
    },
    {
      key: "ads",
      title: "Реклама",
      dependsOn: "ДРР, сопоставление рекламных расходов, риск потерь.",
      tone: byDomain.get("ads") ? domainTone(byDomain.get("ads")) : "not_configured",
      lastSync: byDomain.get("ads")?.last_successful_sync_at ?? byDomain.get("ads")?.last_synced_at ?? null,
      action: { label: "Синхронизировать", href: "/settings" },
    },
    {
      key: "stocks",
      title: "Остатки",
      dependsOn: "Замороженные деньги, сверхзапас, деньги в товаре.",
      tone: byDomain.get("stocks") ? domainTone(byDomain.get("stocks")) : "not_configured",
      lastSync: byDomain.get("stocks")?.last_successful_sync_at ?? byDomain.get("stocks")?.last_synced_at ?? null,
      action: { label: "Синхронизировать", href: "/settings" },
    },
    {
      key: "prices",
      title: "Цены",
      dependsOn: "Безопасная цена, промо-безопасность, маржа.",
      tone: byDomain.get("prices") ? domainTone(byDomain.get("prices")) : "not_configured",
      lastSync: byDomain.get("prices")?.last_successful_sync_at ?? byDomain.get("prices")?.last_synced_at ?? null,
      action: { label: "Синхронизировать", href: "/settings" },
    },
    {
      key: "documents",
      title: "Документы",
      dependsOn: "Дубли, неоплаченные документы, сверка платежей.",
      tone: byDomain.get("documents") ? domainTone(byDomain.get("documents")) : "not_configured",
      lastSync: byDomain.get("documents")?.last_successful_sync_at ?? byDomain.get("documents")?.last_synced_at ?? null,
      action: { label: "Создать задачу", href: "/action-center" },
    },
  ];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Источники финансовых данных</CardTitle>
        <div className="text-xs text-muted-foreground">
          8 источников, от которых зависит расчёт денег. Если источник не подключён или устарел —
          часть цифр остаётся предварительной или недоступна.
        </div>
      </CardHeader>
      <CardContent className="p-3">
        {q.isLoading ? (
          <div className="text-sm text-muted-foreground py-3">Загружаем состояние источников…</div>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {rows.map((r) => {
              const tone = r.tone ?? "not_configured";
              const Icon = TONE_ICON[tone];
              return (
                <div key={r.key} className="rounded-md border p-2.5 space-y-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">{r.title}</div>
                      <div className="text-[11px] text-muted-foreground leading-snug">{r.dependsOn}</div>
                    </div>
                    <Badge variant="outline" className={`text-[10px] gap-1 shrink-0 ${TONE_CLASS[tone]}`}>
                      <Icon className="h-3 w-3" />
                      {TONE_LABEL[tone]}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                    <div>
                      {r.lastSync ? `Обновлено: ${formatDateTime(r.lastSync)}` : (r.reason ?? "Нет данных о синхронизации")}
                    </div>
                    {r.action ? (
                      <Button asChild size="sm" variant="ghost" className="h-6 px-2 text-[11px]">
                        <a href={r.action.href}>{r.action.label}</a>
                      </Button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
