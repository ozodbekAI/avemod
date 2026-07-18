// @ts-nocheck
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useAccounts } from "@/lib/account-context";
import { useAuth } from "@/lib/auth-context";
import { useDateRange } from "@/lib/date-range-context";
import { fetchDoctor } from "@/lib/portal";
import { PageShell, PageHeader } from "@/components/PageShell";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { EndpointError } from "@/components/EndpointError";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { NullValue } from "@/components/money/NullValue";
import { formatMoney } from "@/lib/format";
import { AlertTriangle, ArrowRight, Activity, Stethoscope } from "lucide-react";
import { OperationalFinalBanner } from "@/components/money-ui/OperationalFinalBanner";
import { api, type DashboardDataHealth } from "@/lib/api";
import { API_ENDPOINTS, buildBizQuery } from "@/lib/endpoints";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { LegacyDiagnosticNotice } from "@/components/LegacyDiagnosticNotice";
import { canAccessLegacyDiagnostics } from "@/lib/legacy-diagnostics";

export const Route = createFileRoute("/_authenticated/doctor")({
  component: DoctorPage,
  errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} />,
});

const PRIO_COLORS: Record<string, string> = {
  critical: "bg-destructive/15 text-destructive border-destructive/30",
  high:     "bg-warning/15 text-warning border-warning/30",
  medium:   "bg-primary/10 text-primary border-primary/30",
  low:      "bg-muted text-muted-foreground border-border",
};

const SECTION_TITLES: Record<string, string> = {
  profit_leaks: "Утечки прибыли",
  reputation_risks: "Риски репутации",
  claims_opportunities: "Потенциальные компенсации",
  data_blockers: "Блокеры данных",
  stock_risks: "Риски остатков",
};

function pluralize(n: number, forms: [string, string, string]): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];
  return forms[2];
}

function arrayFromMaybeObject(value: unknown): any[] {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return Object.values(value as Record<string, unknown>);
  return [];
}

function topSectionItems(topSections: unknown): any[] {
  return arrayFromMaybeObject(topSections).flatMap((section: any) => {
    if (Array.isArray(section?.items)) return section.items;
    return [];
  });
}

function visibleTopSections(topSections: unknown): any[] {
  const sections = topSections && typeof topSections === "object" && !Array.isArray(topSections)
    ? Object.entries(topSections as Record<string, any>).map(([key, section]) => ({
        ...(section ?? {}),
        section_key: key,
        title: section?.title ?? SECTION_TITLES[key] ?? key,
      }))
    : arrayFromMaybeObject(topSections);
  return sections.filter((section: any) => {
    const count = Number(section?.count ?? 0);
    const amount = Number(section?.amount ?? section?.money_at_risk_amount ?? 0);
    const hasItems = Array.isArray(section?.items) && section.items.length > 0;
    return count > 0 || amount > 0 || hasItems;
  }).map((section: any) => {
    if (section.title) return section;
    const key = section.section_key;
    return { ...section, title: key ? SECTION_TITLES[key] ?? key : undefined };
  });
}

function todayPlanCount(summary: unknown): number | null {
  if (summary && typeof summary === "object" && "count" in summary) {
    const count = Number((summary as { count?: unknown }).count);
    return Number.isFinite(count) ? count : null;
  }
  return null;
}

function itemData(item: any): Record<string, any> {
  return item?.data && typeof item.data === "object" ? item.data : {};
}

function itemAmount(item: any): number | null {
  const data = itemData(item);
  const raw = item?.money_at_risk_amount
    ?? item?.amount
    ?? item?.expected_effect_amount
    ?? item?.expected_impact_amount
    ?? item?.impact_amount
    ?? item?.estimated_impact_amount
    ?? data.estimated_impact_amount
    ?? data.expected_effect_amount
    ?? data.impact_amount;
  const amount = Number(raw);
  return Number.isFinite(amount) ? amount : null;
}

function itemProductTitle(item: any): string | undefined {
  const data = itemData(item);
  return item?.product_title ?? item?.product_name ?? item?.name ?? data.product_title ?? data.product_name ?? data.name;
}

function itemVendorCode(item: any): string | undefined {
  const data = itemData(item);
  return item?.vendor_code ?? data.vendor_code;
}

function itemExplanation(item: any): string | undefined {
  return item?.explanation ?? item?.reason ?? item?.summary ?? itemData(item).calculation_note;
}

function itemCalculationNote(item: any): string | undefined {
  return item?.calculation_note ?? itemData(item).calculation_note;
}

function itemNextStep(item: any): string | undefined {
  return item?.next_step ?? itemData(item).next_step;
}

function itemChecks(item: any): string[] {
  const raw = item?.checks ?? itemData(item).checks;
  return Array.isArray(raw) ? raw.filter(Boolean).map(String) : [];
}

function itemMetrics(item: any): Array<{ label: string; value: string; tone?: string }> {
  const data = itemData(item);
  const metrics: Array<{ label: string; value: string; tone?: string }> = [];
  const revenue = Number(data.revenue_amount);
  const ads = Number(data.ads_spend_amount);
  const profit = Number(data.profit_amount);
  const drr = Number(data.ads_to_revenue_percent);
  if (Number.isFinite(revenue) && revenue > 0) metrics.push({ label: "Выручка", value: formatMoney(revenue) });
  if (Number.isFinite(ads) && ads > 0) metrics.push({ label: "Реклама", value: formatMoney(ads), tone: "text-warning" });
  if (Number.isFinite(drr) && drr > 0) metrics.push({ label: "DRR", value: `${Math.round(drr)}%`, tone: drr >= 40 ? "text-warning" : undefined });
  if (Number.isFinite(profit)) metrics.push({ label: "Прибыль", value: formatMoney(profit), tone: profit < 0 ? "text-destructive" : "text-success" });
  return metrics;
}


function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return null;
  const m: Record<string, string> = {
    healthy: "bg-success/15 text-success border-success/30",
    ok:      "bg-success/15 text-success border-success/30",
    warning: "bg-warning/15 text-warning border-warning/30",
    risk:    "bg-warning/15 text-warning border-warning/30",
    critical:"bg-destructive/15 text-destructive border-destructive/30",
  };
  const cls = m[status.toLowerCase()] ?? "bg-muted text-muted-foreground border-border";
  return <Badge variant="outline" className={cls}>{status}</Badge>;
}

function DoctorPage() {
  const { activeId } = useAccounts();
  const { user } = useAuth();
  const { from: dateFrom, to: dateTo } = useDateRange();
  const legacyAllowed = canAccessLegacyDiagnostics(user?.is_superuser);
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["portal-doctor", activeId, dateFrom, dateTo],
    queryFn: () => fetchDoctor(activeId, { dateFrom, dateTo }),
    enabled: !!activeId && legacyAllowed,
    staleTime: 60_000,
  });

  const healthQ = useQuery({
    queryKey: ["dashboard-data-health", activeId, dateFrom, dateTo],
    enabled: !!activeId && legacyAllowed,
    queryFn: () => api<DashboardDataHealth>(API_ENDPOINTS.dashboard.dataHealth, {
      query: buildBizQuery({ accountId: activeId, dateFrom, dateTo }),
    }),
    retry: false,
    staleTime: 60_000,
  });

  if (!legacyAllowed) {
    return (
      <PageShell>
        <PageHeader
          title="Диагностика объединена в Центре действий"
          description="Старая диагностика прибыли скрыта, чтобы не дублировать динамические проблемы."
        />
        <Alert data-testid="legacy-doctor-hidden">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Legacy-диагностика недоступна</AlertTitle>
          <AlertDescription className="space-y-3">
            <div>
              Для продавца основной источник проблем — Центр действий и карточка товара.
              Старый доктор доступен только суперпользователю при включённом флаге legacy diagnostics.
            </div>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm">
                <Link to="/action-center">Открыть Центр действий</Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to="/products">Открыть товары</Link>
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="Диагностика прибыли legacy"
        description="Админская проверка старых сигналов прибыли. Для продавца основной путь — Центр действий."
      />

      <LegacyDiagnosticNotice surfaceId="legacy_profit_doctor_route" />

      {!activeId && <NoAccountSelected />}

      {activeId && (
        <DataDependencyNotice
          accountId={activeId}
          domains={["sales", "orders", "finance", "stocks", "ads", "prices", "product_cards"]}
        />
      )}

      {activeId && healthQ.data && (
        <div className="mb-4">
          <OperationalFinalBanner
            operational_trusted={(healthQ.data as any).operational_trusted ?? (healthQ.data as any).business_trusted ?? null}
            financial_final={(healthQ.data as any).financial_final ?? null}
            final_blockers_total={(healthQ.data as any).financial_final_blockers_total ?? null}
          />
        </div>
      )}


      {activeId && isLoading && !error && (
        <div className="space-y-6">
          <Skeleton className="h-32 w-full" />
          <div>
            <Skeleton className="h-4 w-40 mb-3" />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
            </div>
          </div>
          <div>
            <Skeleton className="h-4 w-48 mb-3" />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-32" />)}
            </div>
          </div>
        </div>
      )}

      {activeId && error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Не удалось загрузить диагностику</AlertTitle>
          <AlertDescription className="space-y-2">
            <div>{(error as Error).message}</div>
            <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isFetching}>
              {isFetching ? "Повтор…" : "Повторить"}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {data && (
        <div className="space-y-6">
          {/* Headline + KPIs */}
          <Card>
            <CardContent className="p-5 space-y-3">
              <div className="flex items-start gap-3 flex-wrap">
                <Stethoscope className="h-6 w-6 text-primary mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="text-lg font-semibold leading-tight">
                    {data.headline ?? data.doctor_summary ?? data.summary ?? <NullValue label="Нет диагностики" />}
                  </div>
                  {(data.summary && data.summary !== data.headline) && (
                    <div className="text-sm text-muted-foreground mt-1">{data.summary}</div>
                  )}
                  {data.doctor_summary && data.doctor_summary !== data.headline && data.doctor_summary !== data.summary && (
                    <div className="text-sm text-muted-foreground mt-1">{data.doctor_summary}</div>
                  )}
                  <div className="mt-2 flex items-center gap-3 flex-wrap">
                    <StatusBadge status={data.business_status ?? undefined} />
                    {data.trust_state && (
                      <Badge variant="outline" className="text-[10px] uppercase">
                        Legacy fallback: {data.trust_state}
                      </Badge>
                    )}
                    {healthQ.data?.financial_final === true && (
                      <Badge variant="outline" className="text-[10px] uppercase bg-success/10 text-success border-success/30">
                        Деньги: financial final
                      </Badge>
                    )}
                    <div className="text-sm">
                      <span className="text-muted-foreground">Оценка к проверке: </span>
                      {data.money_at_risk_amount != null
                        ? <span className="font-semibold tabular-nums text-warning">{formatMoney(data.money_at_risk_amount)}</span>
                        : <NullValue />}
                    </div>
                    {data.expected_effect_amount != null && (
                      <div className="rounded-md border border-dashed border-amber-500/45 bg-amber-500/10 px-2 py-1 text-sm text-amber-900 dark:text-amber-200">
                        <span className="text-muted-foreground">Оценка эффекта: </span>
                        <span className="font-semibold tabular-nums">{formatMoney(data.expected_effect_amount)}</span>
                      </div>
                    )}
                  </div>
                  {(data.money_at_risk_calculation_note || data.estimated_impact_calculation_note) && (
                    <div className="text-xs text-muted-foreground mt-2">
                      {data.money_at_risk_calculation_note ?? data.estimated_impact_calculation_note}
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Unavailable sources — soft warning, skip empties */}
          {(() => {
            const us = Array.isArray(data.unavailable_sources)
              ? data.unavailable_sources.filter((s: any) => s && (s.module || s.name || s.source || s.title))
              : [];
            if (us.length === 0) return null;
            return (
              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Некоторые модули ещё не подключены</AlertTitle>
                <AlertDescription>
                  <ul className="list-disc pl-5 mt-1 text-sm space-y-0.5">
                    {us.map((s: any, i: number) => {
                      const name = s.module ?? s.name ?? s.source ?? s.title;
                      const reason = s.reason ?? s.message ?? s.status;
                      return (
                        <li key={i}>
                          <span className="font-medium">{name}</span>
                          {reason && <span className="text-muted-foreground"> — {reason}</span>}
                        </li>
                      );
                    })}
                  </ul>
                </AlertDescription>
              </Alert>
            );
          })()}

          {/* Root causes — grouped */}
          {(() => {
            const raw: any[] = [
              ...(Array.isArray(data.root_causes) ? data.root_causes : []),
              ...topSectionItems(data.top_sections),
            ];
            if (raw.length === 0) return null;

            type Group = {
              key: string;
              title: string;
              diagnosis_type?: string;
              module?: string;
              count: number;
              total_effect: number;
              has_effect: boolean;
              examples: Array<{
                nm_id: string | number;
                name?: string;
                vendor_code?: string;
                amount?: number | null;
                detail?: string;
                next_step?: string;
                checks: string[];
                metrics: Array<{ label: string; value: string; tone?: string }>;
              }>;
              explanation?: string;
            };
            const groups = new Map<string, Group>();
            for (const r of raw) {
              const title = r.title ?? r.cause ?? r.diagnosis ?? r.diagnosis_type ?? "Без названия";
              const dtype = r.diagnosis_type ?? r.cause_type ?? r.type;
              const mod = r.module ?? r.source_module ?? r.source;
              const key = [dtype ?? "", title, mod ?? ""].join("|");
              const effect = itemAmount(r);
              const g: Group = groups.get(key) ?? {
                key, title, diagnosis_type: dtype, module: mod,
                count: 0, total_effect: 0, has_effect: false, examples: [],
                explanation: itemExplanation(r),
              };

              g.count += 1;
              if (effect != null) { g.total_effect += effect; g.has_effect = true; }
              if (r.nm_id != null && g.examples.length < 4 && !g.examples.some((e) => e.nm_id === r.nm_id)) {
                g.examples.push({
                  nm_id: r.nm_id,
                  name: itemProductTitle(r),
                  vendor_code: itemVendorCode(r),
                  amount: effect,
                  detail: r.summary ?? r.reason,
                  next_step: itemNextStep(r),
                  checks: itemChecks(r),
                  metrics: itemMetrics(r),
                });
              }
              if (!g.explanation) g.explanation = itemExplanation(r);
              groups.set(key, g);
            }
            const list = Array.from(groups.values()).sort((a, b) => {
              if (a.has_effect !== b.has_effect) return a.has_effect ? -1 : 1;
              if (b.total_effect !== a.total_effect) return b.total_effect - a.total_effect;
              return b.count - a.count;
            });

            return (
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                  Корневые причины
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {list.map((g) => (
                    <Card key={g.key}>
                      <CardContent className="p-4 space-y-2">
                        <div className="flex items-start justify-between gap-2 flex-wrap">
                          <div className="min-w-0">
                            <div className="font-medium text-sm">{g.title}</div>
                            <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2 flex-wrap">
                              <span className="tabular-nums">{g.count} {pluralize(g.count, ["товар", "товара", "товаров"])}</span>
                              {g.module && <Badge variant="outline" className="text-[10px]">{g.module}</Badge>}
                              {g.diagnosis_type && <Badge variant="outline" className="text-[10px]">{g.diagnosis_type}</Badge>}
                            </div>
                          </div>
                          {g.has_effect && (
                            <span className="text-sm tabular-nums font-semibold text-warning">{formatMoney(g.total_effect)}</span>
                          )}
                        </div>
                        {g.explanation && <div className="text-xs text-muted-foreground">{g.explanation}</div>}
                        {g.examples.length > 0 && (
                          <div className="space-y-1 pt-0.5">
                            <div className="text-[11px] text-muted-foreground">Конкретные товары:</div>
                            {g.examples.map((e) => (
                              <div key={String(e.nm_id)} className="rounded-md border bg-muted/25 px-2 py-1.5 text-xs">
                                <div className="flex items-start justify-between gap-2">
                                  <div className="min-w-0">
                                    <Link
                                      to="/products/$nmId"
                                      params={{ nmId: String(e.nm_id) }}
                                      className="font-medium text-primary hover:underline"
                                    >
                                      {e.name ?? `nm ${e.nm_id}`}
                                    </Link>
                                    <div className="text-[11px] text-muted-foreground">
                                      nm_id {e.nm_id}{e.vendor_code ? ` · ${e.vendor_code}` : ""}
                                    </div>
                                  </div>
                                  {e.amount != null && (
                                    <span className="shrink-0 tabular-nums font-semibold text-warning">{formatMoney(e.amount)}</span>
                                  )}
                                </div>
                                {e.detail && <div className="text-[11px] text-muted-foreground mt-1">{e.detail}</div>}
                                {e.metrics.length > 0 && (
                                  <div className="flex items-center gap-1.5 flex-wrap mt-1.5">
                                    {e.metrics.map((m) => (
                                      <span key={`${e.nm_id}-${m.label}`} className="rounded border bg-background px-1.5 py-0.5 text-[11px]">
                                        <span className="text-muted-foreground">{m.label}: </span>
                                        <span className={`font-semibold tabular-nums ${m.tone ?? ""}`}>{m.value}</span>
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {(e.next_step || e.checks.length > 0) && (
                                  <div className="mt-2 rounded border border-primary/20 bg-primary/5 px-2 py-1.5">
                                    {e.next_step && (
                                      <div className="text-[11px]">
                                        <span className="font-semibold">Как исправить: </span>{e.next_step}
                                      </div>
                                    )}
                                    {e.checks.length > 0 && (
                                      <ul className="mt-1 list-disc pl-4 text-[11px] text-muted-foreground space-y-0.5">
                                        {e.checks.slice(0, 4).map((check) => <li key={check}>{check}</li>)}
                                      </ul>
                                    )}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                        <div className="flex items-center gap-2 pt-1">
                          <Button asChild size="sm" variant="outline" className="h-7 text-xs">
                            <Link to="/action-center">В Центр действий <ArrowRight className="h-3 w-3 ml-1" /></Link>
                          </Button>
                          <Button asChild size="sm" variant="ghost" className="h-7 text-xs">
                            <Link to="/products">К товарам</Link>
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            );
          })()}


          {/* Top profit leaks — grouped by action/root cause to avoid identical card spam */}
          {Array.isArray(data.top_profit_leaks) && data.top_profit_leaks.length > 0 && (() => {
            type Leak = {
              key: string;
              title: string;
              priority?: string;
              summary?: string;
              count: number;
              total_amount: number;
              has_amount: boolean;
              examples: Array<{
                nm_id: string | number;
                name?: string;
                vendor_code?: string;
                amount?: number | null;
                detail?: string;
                note?: string;
                next_step?: string;
                checks: string[];
                metrics: Array<{ label: string; value: string; tone?: string }>;
              }>;
            };
            const groups = new Map<string, Leak>();
            for (const s of data.top_profit_leaks) {
              const title = s.title ?? s.name ?? "Утечка";
              const code  = s.diagnosis_type ?? s.action_type ?? s.code ?? s.root_cause ?? s.cause_code ?? "";
              const key   = `${code}|${title}|${s.priority ?? ""}`;
              const amt   = itemAmount(s);
              const g: Leak = groups.get(key) ?? {
                key, title, priority: s.priority, summary: s.summary,
                count: 0, total_amount: 0, has_amount: false, examples: [],
              };
              g.count += 1;
              if (amt != null) { g.total_amount += amt; g.has_amount = true; }
              if (s.nm_id != null && g.examples.length < 3 && !g.examples.some((e) => e.nm_id === s.nm_id)) {
                g.examples.push({
                  nm_id: s.nm_id,
                  name: itemProductTitle(s),
                  vendor_code: itemVendorCode(s),
                  amount: amt,
                  detail: s.summary ?? s.reason,
                  note: itemCalculationNote(s),
                  next_step: itemNextStep(s),
                  checks: itemChecks(s),
                  metrics: itemMetrics(s),
                });
              }
              if (!g.summary && s.summary) g.summary = s.summary;
              groups.set(key, g);
            }
            const leaks = Array.from(groups.values()).sort((a, b) => {
              if (a.has_amount !== b.has_amount) return a.has_amount ? -1 : 1;
              if (b.total_amount !== a.total_amount) return b.total_amount - a.total_amount;
              return b.count - a.count;
            });
            return (
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                  Где утекает прибыль
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {leaks.map((g) => {
                    const single = g.count === 1 && g.examples[0];
                    const heading = single
                      ? `${g.title} — ${single.name ?? `nm ${single.nm_id}`}`
                      : g.title;
                    return (
                      <Card key={g.key}>
                        <CardContent className="p-4 space-y-2">
                          <div className="flex items-start justify-between gap-2">
                            <div className="font-medium text-sm">{heading}</div>
                            {g.priority && (
                              <Badge variant="outline" className={PRIO_COLORS[g.priority] ?? ""}>{g.priority}</Badge>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground flex items-center gap-2 flex-wrap">
                            {g.count > 1 && (
                              <span className="tabular-nums">
                                {g.count} {pluralize(g.count, ["товар", "товара", "товаров"])}
                              </span>
                            )}
                            {g.summary && <span>{g.summary}</span>}
                          </div>
                          {g.has_amount && (
                            <div className="text-sm tabular-nums font-semibold text-warning">
                              {formatMoney(g.total_amount)}
                            </div>
                          )}
                          {g.examples.length > 0 && (
                            <div className="space-y-1 pt-0.5">
                              <div className="text-[11px] text-muted-foreground">
                                {g.count > g.examples.length ? "Топ примеры:" : "Товары:"}
                              </div>
                              {g.examples.map((e) => (
                                <div key={String(e.nm_id)} className="rounded-md border bg-muted/25 px-2 py-1.5 text-xs">
                                  <div className="flex items-start justify-between gap-2">
                                    <div className="min-w-0">
                                      <Link
                                        to="/products/$nmId"
                                        params={{ nmId: String(e.nm_id) }}
                                        className="font-medium text-primary hover:underline"
                                      >
                                        {e.name ?? `nm ${e.nm_id}`}
                                      </Link>
                                      <div className="text-[11px] text-muted-foreground">
                                        nm_id {e.nm_id}{e.vendor_code ? ` · ${e.vendor_code}` : ""}
                                      </div>
                                    </div>
                                    {e.amount != null && (
                                      <span className="shrink-0 tabular-nums font-semibold text-warning">{formatMoney(e.amount)}</span>
                                    )}
                                  </div>
                                  {e.detail && <div className="text-[11px] text-muted-foreground mt-1">{e.detail}</div>}
                                  {e.metrics.length > 0 && (
                                    <div className="flex items-center gap-1.5 flex-wrap mt-1.5">
                                      {e.metrics.map((m) => (
                                        <span key={`${e.nm_id}-${m.label}`} className="rounded border bg-background px-1.5 py-0.5 text-[11px]">
                                          <span className="text-muted-foreground">{m.label}: </span>
                                          <span className={`font-semibold tabular-nums ${m.tone ?? ""}`}>{m.value}</span>
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                  {(e.next_step || e.checks.length > 0) && (
                                    <div className="mt-2 rounded border border-primary/20 bg-primary/5 px-2 py-1.5">
                                      {e.next_step && (
                                        <div className="text-[11px]">
                                          <span className="font-semibold">Как исправить: </span>{e.next_step}
                                        </div>
                                      )}
                                      {e.checks.length > 0 && (
                                        <ul className="mt-1 list-disc pl-4 text-[11px] text-muted-foreground space-y-0.5">
                                          {e.checks.slice(0, 4).map((check) => <li key={check}>{check}</li>)}
                                        </ul>
                                      )}
                                    </div>
                                  )}
                                  {e.note && <div className="text-[11px] text-muted-foreground mt-0.5">{e.note}</div>}
                                </div>
                              ))}
                            </div>
                          )}
                          <div className="flex items-center gap-2 pt-1">
                            <Button asChild size="sm" variant="outline" className="h-7 text-xs">
                              <Link to="/action-center">Открыть в Центре действий <ArrowRight className="h-3 w-3 ml-1" /></Link>
                            </Button>
                            {single && (
                              <Button asChild size="sm" variant="ghost" className="h-7 text-xs">
                                <Link to="/products/$nmId" params={{ nmId: String(single.nm_id) }}>Карточка</Link>
                              </Button>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              </div>
            );
          })()}

          {/* Top sections (legacy) */}
          {visibleTopSections(data.top_sections).length > 0 && (
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                Главные зоны риска
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {visibleTopSections(data.top_sections).map((s: any, i: number) => (
                  <Card key={i}>
                    <CardContent className="p-4 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="font-medium text-sm">{s.title ?? s.name ?? `Секция ${i + 1}`}</div>
                        {s.priority && (
                          <Badge variant="outline" className={PRIO_COLORS[s.priority] ?? ""}>{s.priority}</Badge>
                        )}
                      </div>
                      {s.summary && <div className="text-xs text-muted-foreground">{s.summary}</div>}
                      {(s.amount != null || s.money_at_risk_amount != null) && (
                        <div className="text-sm tabular-nums font-semibold">
                          {formatMoney(s.amount ?? s.money_at_risk_amount)}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Today plan */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                План на сегодня
              </h2>
              {todayPlanCount(data.today_plan_summary) != null && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {todayPlanCount(data.today_plan_summary)} {pluralize(todayPlanCount(data.today_plan_summary) ?? 0, ["задача", "задачи", "задач"])}
                </span>
              )}
            </div>
            {Array.isArray(data.today_plan) && data.today_plan.length > 0 ? (() => {
              type Plan = {
                key: string;
                title: string;
                priority?: string;
                reason?: string;
                next_step?: string;
                confidence?: any;
                count: number;
                total_effect: number;
                has_effect: boolean;
                examples: Array<{ nm_id: string | number; name?: string; vendor_code?: string; amount?: number | null; detail?: string }>;
              };
              const groups = new Map<string, Plan>();
              for (const p of data.today_plan) {
                const title = p.title ?? p.action_title ?? "Действие";
                const code  = p.action_type ?? p.code ?? "";
                const key   = `${code}|${title}|${p.priority ?? ""}`;
                const eff   = itemAmount(p);
                const g: Plan = groups.get(key) ?? {
                  key, title, priority: p.priority, reason: p.reason,
                  next_step: p.next_step, confidence: p.confidence,
                  count: 0, total_effect: 0, has_effect: false, examples: [],
                };
                g.count += 1;
                if (eff != null) { g.total_effect += eff; g.has_effect = true; }
                if (p.nm_id != null && g.examples.length < 4 && !g.examples.some((e) => e.nm_id === p.nm_id)) {
                  g.examples.push({
                    nm_id: p.nm_id,
                    name: itemProductTitle(p),
                    vendor_code: itemVendorCode(p),
                    amount: eff,
                    detail: p.summary ?? p.reason,
                  });
                }
                if (!g.reason && p.reason) g.reason = p.reason;
                if (!g.next_step && p.next_step) g.next_step = p.next_step;
                if (g.confidence == null && p.confidence != null) g.confidence = p.confidence;
                groups.set(key, g);
              }
              const plans = Array.from(groups.values()).sort((a, b) => {
                if (a.has_effect !== b.has_effect) return a.has_effect ? -1 : 1;
                if (b.total_effect !== a.total_effect) return b.total_effect - a.total_effect;
                return b.count - a.count;
              });
              return (
                <div className="space-y-2">
                  {plans.map((g) => {
                    const single = g.count === 1;
                    return (
                      <Card key={g.key}>
                        <CardContent className="p-4 flex items-start gap-3">
                          <Activity className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              {g.priority && (
                                <Badge variant="outline" className={PRIO_COLORS[g.priority] ?? ""}>{g.priority}</Badge>
                              )}
                              <div className="font-medium text-sm">
                                {g.title}
                                {!single && (
                                  <span className="text-muted-foreground font-normal">
                                    {" "}— {g.count} {pluralize(g.count, ["товар", "товара", "товаров"])}
                                  </span>
                                )}
                              </div>
                              {g.confidence != null && (
                                <Badge variant="outline" className="text-[10px]">
                                  Уверенность: {typeof g.confidence === "number"
                                    ? `${Math.round(g.confidence * (g.confidence <= 1 ? 100 : 1))}%`
                                    : String(g.confidence)}
                                </Badge>
                              )}
                            </div>
                            {g.reason && (
                              <div className="text-xs text-muted-foreground mt-1">
                                <span className="font-medium">Почему: </span>{g.reason}
                              </div>
                            )}
                            {g.next_step && (
                              <div className="text-xs text-muted-foreground mt-0.5">
                                <span className="font-medium">Шаг: </span>{g.next_step}
                              </div>
                            )}
                            {g.has_effect && (
                              <div className="mt-1 inline-flex rounded-md border border-dashed border-amber-500/45 bg-amber-500/10 px-2 py-1 text-xs font-medium tabular-nums text-amber-800 dark:text-amber-200">
                                Оценка эффекта: {formatMoney(g.total_effect)}
                              </div>
                            )}
                            {g.examples.length > 0 && (
                              <div className="space-y-1 mt-1.5">
                                <div className="text-[11px] text-muted-foreground">
                                  {single ? "Товар:" : "Примеры:"}
                                </div>
                                {g.examples.map((e) => (
                                  <div key={String(e.nm_id)} className="rounded-md border bg-muted/25 px-2 py-1.5 text-xs">
                                    <div className="flex items-start justify-between gap-2">
                                      <div className="min-w-0">
                                        <Link
                                          to="/products/$nmId"
                                          params={{ nmId: String(e.nm_id) }}
                                          className="font-medium text-primary hover:underline"
                                        >
                                          {e.name ?? `nm ${e.nm_id}`}
                                        </Link>
                                        <div className="text-[11px] text-muted-foreground">
                                          nm_id {e.nm_id}{e.vendor_code ? ` · ${e.vendor_code}` : ""}
                                        </div>
                                      </div>
                                      {e.amount != null && (
                                        <span className="shrink-0 rounded border border-dashed border-amber-500/45 bg-amber-500/10 px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-amber-800 dark:text-amber-200">{formatMoney(e.amount)}</span>
                                      )}
                                    </div>
                                    {e.detail && <div className="text-[11px] text-muted-foreground mt-1">{e.detail}</div>}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="flex flex-col gap-1 items-end">
                            {single && g.examples[0]?.nm_id != null && (
                              <Button asChild size="sm" variant="outline" className="h-7 text-xs">
                                <Link to="/products/$nmId" params={{ nmId: String(g.examples[0].nm_id) }}>
                                  Карточка <ArrowRight className="h-3 w-3 ml-1" />
                                </Link>
                              </Button>
                            )}
                            <Button asChild size="sm" variant="ghost" className="h-7 text-xs">
                              <Link to="/action-center">
                                {single ? "В Центр действий" : `Все ${g.count} в Центр действий`}
                              </Link>
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              );
            })() : (
              <Card><CardContent className="p-6 text-sm text-muted-foreground text-center">Сегодня действий нет.</CardContent></Card>
            )}
          </div>
        </div>
      )}
    </PageShell>
  );
}
