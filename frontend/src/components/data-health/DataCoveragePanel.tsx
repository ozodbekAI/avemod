import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Clock,
  Database,
  Loader2,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { toast } from "sonner";

import { api, apiList, ApiError } from "@/lib/api";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { formatDateTime, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export type FreshnessStatus = "fresh" | "stale" | "missing" | "failed";
export type PermissionStatus = "ok" | "missing" | "unknown";

export interface DataSyncDomainStatus {
  domain: string;
  status?: string | null;
  token_category?: string | null;
  token_configured?: boolean | null;
  configured?: boolean | null;
  permission_status?: PermissionStatus | string | null;
  permission_ok?: boolean | null;
  token_ok?: boolean | null;
  last_synced_at?: string | null;
  last_successful_sync_at?: string | null;
  last_failed_sync_at?: string | null;
  data_watermark_at?: string | null;
  last_error_text?: string | null;
  last_error_human_message?: string | null;
  rows_loaded?: number | null;
  raw_response_count?: number | null;
  freshness_status?: FreshnessStatus | string | null;
  next_action?: string | null;
  next_recommended_action?: string | null;
  required_for?: string[];
}

export interface DataSyncStatusResponse {
  account_id: number;
  overall_state?: "ok" | "warning" | "failed" | "unknown" | string;
  user_facing_status?: string | null;
  has_active_sync?: boolean | null;
  has_stale_running_sync?: boolean | null;
  data_alignment_status?:
    | "aligned"
    | "new_account"
    | "misaligned"
    | "insufficient_data"
    | string
    | null;
  data_alignment_warnings?: string[];
  data_alignment_domains?: string[];
  last_calculated_at?: string | null;
  calculation_cache_status?:
    | "fresh"
    | "stale"
    | "missing"
    | "unknown"
    | string
    | null;
  calculation_refresh_status?:
    | "ready"
    | "pending"
    | "blocked"
    | "stale"
    | "unknown"
    | string
    | null;
  calculation_refresh_message?: string | null;
  domains: DataSyncDomainStatus[];
  current_sync_runs?: VisibleSyncRun[];
  queued_syncs?: VisibleSyncRun[];
  active_sync_progress?: VisibleSyncRun[];
  warnings?: string[];
}

type FallbackPage<T> = { items?: T[] };

type SyncFallbackCursor = {
  domain?: string | null;
  source?: string | null;
  module?: string | null;
  last_synced_at?: string | null;
  updated_at?: string | null;
  status?: string | null;
};

type SyncFallbackRun = {
  domain?: string | null;
  source?: string | null;
  module?: string | null;
  status?: string | null;
  error?: string | null;
  error_text?: string | null;
};

const ACTIVE_SYNC_STATUSES = new Set(["queued", "running", "in_progress"]);
const EMPTY_DOMAIN_SET = new Set<string>();

type VisibleSyncRun = {
  id: number;
  domain: string;
  status: string;
  trigger?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  details?: Record<string, unknown> | null;
  error_text?: string | null;
};

const DOMAIN_LABELS: Record<string, string> = {
  product_cards: "Карточки товаров",
  sales: "Продажи",
  orders: "Заказы",
  finance: "Финансы Вайлдберриз",
  stocks: "Остатки",
  ads: "Реклама",
  prices: "Цены",
  promotions: "Акции WB",
  analytics: "Аналитика",
  tariffs: "Тарифы",
  supplies: "Поставки",
  logistics: "Логистика",
  documents: "Документы",
  reputation: "Отзывы и вопросы",
};

const TOKEN_CATEGORY_LABELS: Record<string, string> = {
  ads: "Реклама",
  analytics: "Аналитика",
  content: "Контент",
  documents: "Документы",
  finance: "Финансы",
  marketplace: "Маркетплейс",
  prices: "Цены",
  promotions: "Акции",
  statistics: "Статистика",
  supplies: "Поставки",
  tariffs: "Тарифы",
};

const DEFAULT_DOMAINS = [
  "product_cards",
  "sales",
  "orders",
  "finance",
  "stocks",
  "ads",
  "prices",
  "promotions",
  "analytics",
  "supplies",
  "tariffs",
  "logistics",
  "documents",
  "reputation",
];

function domainLabel(domain: string): string {
  return DOMAIN_LABELS[domain] ?? domain.replaceAll("_", " ");
}

function tokenCategoryLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const normalized = value.toLowerCase();
  return TOKEN_CATEGORY_LABELS[normalized] ?? value.replaceAll("_", " ");
}

function isActiveSyncRun(run: VisibleSyncRun | null | undefined): boolean {
  return ACTIVE_SYNC_STATUSES.has(String(run?.status ?? "").toLowerCase());
}

function latestDomainRun(
  runs: VisibleSyncRun[],
  domain: string,
): VisibleSyncRun | null {
  const domainRuns = runs.filter((run) => run.domain === domain);
  return (
    domainRuns.find((run) => String(run.status).toLowerCase() === "running") ??
    domainRuns.find((run) => String(run.status).toLowerCase() === "queued") ??
    domainRuns[0] ??
    null
  );
}

function pageItems<T>(value: T[] | FallbackPage<T>): T[] {
  return Array.isArray(value) ? value : (value.items ?? []);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function cleanTechnicalCopy(value: string | null | undefined): string {
  return String(value ?? "")
    .replace(/WB API request failed:?/gi, "Запрос к Вайлдберриз не прошел.")
    .replace(/\bWB\b/g, "Вайлдберриз")
    .replace(/\bAPI\b/g, "интерфейс");
}

function cleanAlignmentWarning(value: string): string {
  return cleanTechnicalCopy(value)
    .replace(/^Sales\s*\/\s*orders:/i, "Продажи и заказы:")
    .replace(/^Money sources:/i, "Денежные источники:")
    .replace(/`sales`/gi, "продажи")
    .replace(/`orders`/gi, "заказы")
    .replace(/`finance`/gi, "финансы")
    .replace(/`stocks`/gi, "остатки")
    .replace(/продажи отстаёт от заказы/gi, "продажи отстают от заказов")
    .replace(/финансы отстаёт от заказы/gi, "финансы отстают от заказов")
    .replace(/остатки отстаёт от заказы/gi, "остатки отстают от заказов");
}

export async function fetchDataSyncStatus(
  accountId: number,
): Promise<DataSyncStatusResponse> {
  try {
    const res = await api<DataSyncStatusResponse | DataSyncDomainStatus[]>(
      API_ENDPOINTS.portalExtras.dataSyncStatus,
      {
        query: { account_id: accountId },
      },
    );
    if (Array.isArray(res))
      return { account_id: accountId, domains: res, overall_state: "unknown" };
    return { ...res, domains: Array.isArray(res?.domains) ? res.domains : [] };
  } catch (e) {
    if (!(e instanceof ApiError) || (e.status !== 404 && e.status !== 501))
      throw e;
    const [cursors, runs] = await Promise.all([
      api<SyncFallbackCursor[] | FallbackPage<SyncFallbackCursor>>(
        API_ENDPOINTS.sync.cursors,
        {
          query: { account_id: accountId },
        },
      ).catch(() => []),
      api<SyncFallbackRun[] | FallbackPage<SyncFallbackRun>>(
        API_ENDPOINTS.sync.runs,
        {
          query: { account_id: accountId },
        },
      ).catch(() => []),
    ]);
    const cursorList = pageItems(cursors);
    const runList = pageItems(runs);
    const byDomain = new Map<string, DataSyncDomainStatus>();
    for (const c of cursorList) {
      const d = String(c.domain ?? c.source ?? c.module ?? "").toLowerCase();
      if (!d) continue;
      byDomain.set(d, {
        domain: d,
        last_synced_at: c.last_synced_at ?? c.updated_at ?? null,
        last_successful_sync_at: c.last_synced_at ?? null,
        status: c.status ?? null,
        configured: true,
        token_configured: true,
        permission_status: "unknown",
        freshness_status: c.last_synced_at ? "stale" : "missing",
      });
    }
    for (const r of runList) {
      const d = String(r.domain ?? r.source ?? r.module ?? "").toLowerCase();
      if (!d) continue;
      const existing = byDomain.get(d) ?? { domain: d };
      if (r.status === "failed" || r.error || r.error_text) {
        existing.last_error_human_message =
          r.error_text ?? r.error ?? "Последний запуск завершился ошибкой";
        existing.freshness_status = "failed";
      }
      existing.status = existing.status ?? r.status;
      byDomain.set(d, existing);
    }
    return {
      account_id: accountId,
      domains: Array.from(byDomain.values()),
      overall_state: "unknown",
    };
  }
}

function freshnessLabel(value: unknown): string {
  switch (value) {
    case "fresh":
      return "свежие";
    case "stale":
      return "устарели";
    case "failed":
      return "ошибка";
    case "missing":
      return "нет данных";
    default:
      return "неизвестно";
  }
}

function freshnessTone(value: unknown): string {
  switch (value) {
    case "fresh":
      return "border-success text-success";
    case "stale":
      return "border-warning text-warning";
    case "failed":
      return "border-destructive text-destructive";
    case "missing":
      return "border-muted-foreground/40 text-muted-foreground";
    default:
      return "border-muted-foreground/40 text-muted-foreground";
  }
}

function isAlignmentDomain(
  row: DataSyncDomainStatus,
  alignmentDomains: Set<string> = EMPTY_DOMAIN_SET,
): boolean {
  return alignmentDomains.has(row.domain);
}

function needsAttention(
  row: DataSyncDomainStatus,
  alignmentDomains: Set<string> = EMPTY_DOMAIN_SET,
): boolean {
  return (
    ACTIVE_SYNC_STATUSES.has(String(row.status ?? "").toLowerCase()) ||
    row.permission_status === "missing" ||
    row.freshness_status !== "fresh" ||
    isAlignmentDomain(row, alignmentDomains)
  );
}

function canStartSync(
  row: DataSyncDomainStatus,
  alignmentDomains: Set<string> = EMPTY_DOMAIN_SET,
): boolean {
  return (
    row.permission_status !== "missing" &&
    !ACTIVE_SYNC_STATUSES.has(String(row.status ?? "").toLowerCase()) &&
    (row.freshness_status !== "fresh" ||
      isAlignmentDomain(row, alignmentDomains))
  );
}

function syncableDomains(
  rows: DataSyncDomainStatus[],
  alignmentDomains: Set<string> = EMPTY_DOMAIN_SET,
): string[] {
  return Array.from(
    new Set(
      rows
        .filter((row) => canStartSync(row, alignmentDomains))
        .map((row) => row.domain),
    ),
  ).filter(Boolean);
}

function permissionLabel(value: unknown): string {
  switch (String(value ?? "").toLowerCase()) {
    case "ok":
      return "есть";
    case "missing":
      return "нет";
    case "unknown":
    case "":
      return "неизвестно";
    default:
      return "требует проверки";
  }
}

async function triggerSyncForDomains(
  accountId: number,
  domains: string[],
): Promise<VisibleSyncRun[]> {
  const uniqueDomains = Array.from(new Set(domains)).filter(Boolean);
  return Promise.all(
    uniqueDomains.map((domain) =>
      api<VisibleSyncRun>(API_ENDPOINTS.sync.trigger, {
        method: "POST",
        body: { account_id: accountId, domain },
      }),
    ),
  );
}

function rowMessage(
  row: DataSyncDomainStatus,
  alignmentDomains: Set<string> = EMPTY_DOMAIN_SET,
): string {
  if (ACTIVE_SYNC_STATUSES.has(String(row.status ?? "").toLowerCase())) {
    return "Синхронизация идёт. Расчёты обновятся после завершения.";
  }
  if (row.permission_status === "missing") {
    return `Нужна категория токена Вайлдберриз: ${tokenCategoryLabel(row.token_category ?? row.domain)}.`;
  }
  if (isAlignmentDomain(row, alignmentDomains)) {
    return "Дата данных отстаёт от других источников. Перезапустите синхронизацию.";
  }
  if (row.freshness_status === "failed")
    return cleanTechnicalCopy(
      row.last_error_human_message ??
        row.last_error_text ??
        "Последняя синхронизация завершилась ошибкой.",
    );
  if (row.freshness_status === "stale")
    return `Последняя успешная синхронизация: ${formatDateTime(row.last_successful_sync_at ?? row.last_synced_at)}`;
  if (row.freshness_status === "missing") return "Источник еще не загружался.";
  return `Обновлено: ${formatDateTime(row.last_successful_sync_at ?? row.last_synced_at)}`;
}

function recommendedAction(
  row: DataSyncDomainStatus,
  alignmentDomains: Set<string> = EMPTY_DOMAIN_SET,
): string | null {
  if (isAlignmentDomain(row, alignmentDomains)) {
    return `Перезапустить синхронизацию: ${domainLabel(row.domain)}.`;
  }
  return row.next_recommended_action ?? null;
}

function calculationStatusLabel(value: unknown): string {
  switch (String(value ?? "").toLowerCase()) {
    case "fresh":
      return "готов";
    case "stale":
      return "устарел";
    case "missing":
      return "ещё не выполнен";
    default:
      return "неизвестно";
  }
}

function orderedRows(
  rows: DataSyncDomainStatus[],
  domains?: string[],
): DataSyncDomainStatus[] {
  const byDomain = new Map(rows.map((row) => [row.domain, row]));
  const order = domains?.length ? domains : DEFAULT_DOMAINS;
  const primary = order.map(
    (domain) =>
      byDomain.get(domain) ?? {
        domain,
        freshness_status: "missing",
        permission_status: "unknown",
      },
  );
  const rest = rows.filter((row) => !order.includes(row.domain));
  return [...primary, ...rest];
}

export function DataCoveragePanel({
  accountId,
  domains,
  compact = false,
  title = "Покрытие данных",
  description = "Свежесть источников Вайлдберриз и права токенов по этому кабинету.",
  className,
}: {
  accountId: number | null | undefined;
  domains?: string[];
  compact?: boolean;
  title?: string;
  description?: string;
  className?: string;
}) {
  const qc = useQueryClient();
  const enabled = !!accountId;
  const q = useQuery({
    queryKey: ["data-sync-status", accountId],
    enabled,
    queryFn: () => fetchDataSyncStatus(accountId!),
    staleTime: 30_000,
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data as DataSyncStatusResponse | undefined;
      const active =
        data?.has_active_sync ||
        (data?.active_sync_progress?.length ?? 0) > 0 ||
        (data?.queued_syncs?.length ?? 0) > 0;
      return active ? 2_000 : 30_000;
    },
  });

  const rows = useMemo(
    () => orderedRows(q.data?.domains ?? [], domains),
    [q.data?.domains, domains],
  );
  const alignmentDomainSet = useMemo(
    () => new Set(q.data?.data_alignment_domains ?? []),
    [q.data?.data_alignment_domains],
  );
  const badRows = rows.filter((row) => needsAttention(row, alignmentDomainSet));
  const domainsToSync = syncableDomains(badRows, alignmentDomainSet);
  const activeSync = Boolean(
    q.data?.has_active_sync ||
    (q.data?.active_sync_progress?.length ?? 0) > 0 ||
    (q.data?.queued_syncs?.length ?? 0) > 0,
  );
  const calculationMessage = q.data?.calculation_refresh_message ?? null;
  const calculationMeta = q.data?.last_calculated_at
    ? `Последний расчёт: ${formatDateTime(q.data.last_calculated_at)} · ${calculationStatusLabel(q.data.calculation_cache_status)}`
    : "Последний расчёт: ещё не выполнен";
  const alignmentWarnings = q.data?.data_alignment_warnings ?? [];
  const trigger = useMutation({
    mutationFn: async (domain?: string) =>
      triggerSyncForDomains(accountId!, domain ? [domain] : domainsToSync),
    onSuccess: () => {
      toast.success("Синхронизация запущена");
      qc.invalidateQueries({ queryKey: ["data-sync-status"] });
      qc.invalidateQueries({ queryKey: ["topbar-sync-status"] });
      qc.invalidateQueries({ queryKey: ["topbar-sync-runs"] });
      qc.invalidateQueries({ queryKey: ["topbar-sync-cursors"] });
    },
    onError: (error: unknown) =>
      toast.error(errorMessage(error, "Не удалось запустить синхронизацию")),
  });

  if (!enabled) return null;

  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <Database className="h-4 w-4" />
            {title}
          </CardTitle>
          {!compact ? (
            <CardDescription className="text-xs mt-1">
              {description}
            </CardDescription>
          ) : null}
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={trigger.isPending || domainsToSync.length === 0}
          onClick={() => trigger.mutate(undefined)}
        >
          {trigger.isPending ? (
            <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
          )}
          Синхронизировать
        </Button>
      </CardHeader>
      <CardContent>
        {q.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : q.isError ? (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Статус источников недоступен</AlertTitle>
            <AlertDescription>
              Не удалось прочитать состояние источников данных.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="space-y-3">
            {calculationMessage ? (
              <Alert
                className={cn(
                  "border-border/70 bg-muted/30",
                  q.data?.calculation_refresh_status === "pending" &&
                    "border-primary/30 bg-primary/5",
                  q.data?.calculation_refresh_status === "blocked" &&
                    "border-destructive/35 bg-destructive/5",
                )}
              >
                {activeSync ? (
                  <RefreshCw className="h-4 w-4 animate-spin text-primary" />
                ) : q.data?.calculation_refresh_status === "blocked" ? (
                  <AlertTriangle className="h-4 w-4 text-destructive" />
                ) : (
                  <Database className="h-4 w-4" />
                )}
                <AlertTitle>
                  {q.data?.user_facing_status ?? "Статус данных"}
                </AlertTitle>
                <AlertDescription className="text-xs">
                  <div>{calculationMessage}</div>
                  {!compact ? (
                    <div className="mt-1 text-muted-foreground">
                      {calculationMeta}
                    </div>
                  ) : null}
                  {alignmentWarnings.length > 0 ? (
                    <div className="mt-1 space-y-0.5">
                      {alignmentWarnings.slice(0, 3).map((message) => (
                        <div key={message}>{cleanAlignmentWarning(message)}</div>
                      ))}
                    </div>
                  ) : null}
                </AlertDescription>
              </Alert>
            ) : null}
            {!calculationMessage && !compact ? (
              <div className="text-xs text-muted-foreground">
                {calculationMeta}
              </div>
            ) : null}
            <div
              className={cn(
                "grid gap-2",
                compact ? "md:grid-cols-2" : "md:grid-cols-3",
              )}
            >
              {rows.map((row) => (
                <div key={row.domain} className="rounded-md border p-3 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">
                        {domainLabel(row.domain)}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {rowMessage(row, alignmentDomainSet)}
                      </div>
                    </div>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px] shrink-0",
                        freshnessTone(row.freshness_status),
                      )}
                    >
                      {freshnessLabel(row.freshness_status)}
                    </Badge>
                  </div>
                  {!compact ? (
                    <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
                      <div>
                        Токен:{" "}
                        <span className="text-foreground">
                          {tokenCategoryLabel(row.token_category)}
                        </span>
                      </div>
                      <div>
                        Права:{" "}
                        <span className="text-foreground">
                          {permissionLabel(row.permission_status)}
                        </span>
                      </div>
                      <div>
                        Строки:{" "}
                        <span className="text-foreground">
                          {formatNumber(row.rows_loaded ?? 0)}
                        </span>
                      </div>
                      <div>
                        Ответы:{" "}
                        <span className="text-foreground">
                          {formatNumber(row.raw_response_count ?? 0)}
                        </span>
                      </div>
                      <div className="col-span-2">
                        Данные до:{" "}
                        <span className="text-foreground">
                          {formatDateTime(row.data_watermark_at)}
                        </span>
                      </div>
                    </div>
                  ) : null}
                  {recommendedAction(row, alignmentDomainSet) &&
                  needsAttention(row, alignmentDomainSet) ? (
                    <div className="mt-2 text-[11px] text-primary">
                      {recommendedAction(row, alignmentDomainSet)}
                    </div>
                  ) : null}
                  {canStartSync(row, alignmentDomainSet) ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2 h-7 text-xs"
                      disabled={trigger.isPending}
                      onClick={() => trigger.mutate(row.domain)}
                    >
                      {trigger.isPending ? (
                        <Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3 w-3 mr-1.5" />
                      )}
                      Запустить
                    </Button>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        )}
        {!compact && badRows.length > 0 ? (
          <Alert className="mt-3 border-warning/40 bg-warning/5">
            <ShieldAlert className="h-4 w-4 text-warning" />
            <AlertTitle>Есть источники, влияющие на расчеты</AlertTitle>
            <AlertDescription className="text-xs">
              {badRows
                .slice(0, 3)
                .map(
                  (row) =>
                    `${domainLabel(row.domain)}: ${rowMessage(row, alignmentDomainSet)}`,
                )
                .join(" ")}
            </AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function DataDependencyNotice(_: {
  accountId: number | null | undefined;
  domains: string[];
  className?: string;
}) {
  return null;
}
