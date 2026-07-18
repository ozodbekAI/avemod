import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  DatabaseZap,
  Loader2,
  Megaphone,
  PackageSearch,
  ReceiptText,
  RefreshCw,
  WalletCards,
} from "lucide-react";

import { API_ENDPOINTS } from "@/lib/endpoints";
import { apiList, type SyncCursor, type SyncRun } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { formatSyncTime, type DataFreshnessDomain } from "@/lib/owner-ux";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";

type FreshnessState = "ok" | "warn" | "error" | "missing";

type FreshnessItem = {
  key: DataFreshnessDomain;
  label: string;
  Icon: LucideIcon;
  lastSyncedAt: string | null;
  status: string | null;
  source: string | null;
  state: FreshnessState;
};

const ACTIVE_SYNC_STATUSES = new Set(["queued", "running", "in_progress"]);

const DOMAINS: Array<{
  key: DataFreshnessDomain;
  label: string;
  Icon: LucideIcon;
  match: string[];
}> = [
  {
    key: "sales",
    label: "Продажи",
    Icon: BarChart3,
    match: ["sales", "sale", "orders", "realization"],
  },
  {
    key: "finance",
    label: "Финансы",
    Icon: WalletCards,
    match: ["finance", "report", "reconciliation"],
  },
  {
    key: "stocks",
    label: "Остатки",
    Icon: PackageSearch,
    match: ["stock", "warehouse", "inventory"],
  },
  {
    key: "ads",
    label: "Реклама",
    Icon: Megaphone,
    match: ["ads", "advert", "campaign", "promotion"],
  },
  {
    key: "costs",
    label: "Себестоимость",
    Icon: ReceiptText,
    match: ["cost", "cogs", "manual_cost"],
  },
];

const SYNC_STAGE_LABELS: Record<string, string> = {
  queued: "Ожидает запуска",
  running: "Синхронизация запущена",
  completed: "Синхронизация завершена",
  partial: "Завершено частично",
  failed: "Синхронизация завершилась ошибкой",
  skipped: "Другой запуск уже выполняется",
  finance_prepare: "Подготовка периода",
  finance_balance: "Баланс Вайлдберриз",
  finance_balance_done: "Баланс Вайлдберриз загружен",
  finance_reports: "Список финансовых отчетов",
  finance_reports_done: "Финансовые отчеты найдены",
  finance_details: "Детализация реализации",
  finance_details_done: "Детализация реализации загружена",
  finance_acquiring: "Отчеты эквайринга",
  finance_acquiring_details: "Детализация эквайринга",
  finance_acquiring_done: "Эквайринг загружен",
  finance_acquiring_failed: "Эквайринг недоступен или завершился ошибкой",
  finance_cursors: "Сохранение курсоров",
  finance_rate_limit_wait: "Пауза из-за лимита Вайлдберриз",
  finance_rate_limited: "Вайлдберриз ограничил частоту запросов",
};

const DOMAIN_LABELS: Record<string, string> = {
  product_cards: "Карточки товаров",
  sales: "Продажи",
  orders: "Заказы",
  finance: "Финансы Вайлдберриз",
  stocks: "Остатки",
  ads: "Реклама",
  prices: "Цены",
  analytics: "Аналитика",
  tariffs: "Тарифы",
  supplies: "Поставки",
  documents: "Документы",
  reputation: "Отзывы и вопросы",
};

function domainLabel(domain: string): string {
  return DOMAIN_LABELS[domain] ?? domain.replaceAll("_", " ");
}

function toTs(value: string | null | undefined): number {
  if (!value) return 0;
  const ts = Date.parse(value);
  return Number.isFinite(ts) ? ts : 0;
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function isActiveSyncRun(run: SyncRun | null | undefined): boolean {
  return ACTIVE_SYNC_STATUSES.has(String(run?.status ?? "").toLowerCase());
}

function syncStatusLabel(status: unknown): string {
  switch (String(status ?? "").toLowerCase()) {
    case "queued":
      return "в очереди";
    case "running":
    case "in_progress":
      return "выполняется";
    case "completed":
    case "success":
    case "done":
      return "завершено";
    case "partial":
      return "частично";
    case "failed":
    case "error":
      return "ошибка";
    case "skipped":
      return "пропущено";
    default:
      return "неизвестно";
  }
}

function syncProgressPercent(run: SyncRun | null | undefined): number {
  if (!run) return 0;
  const details = run.details ?? {};
  const raw =
    numericValue(details.progress_percent) ??
    numericValue(details.progress) ??
    numericValue(details.percent);
  if (raw != null) {
    const normalized = raw <= 1 ? raw * 100 : raw;
    return Math.max(0, Math.min(100, Math.round(normalized)));
  }
  const status = String(run.status ?? "").toLowerCase();
  if (status === "queued") return 3;
  if (status === "running" || status === "in_progress") return 25;
  if (status === "completed" || status === "partial" || status === "failed")
    return 100;
  return 0;
}

function syncStageLabel(run: SyncRun | null | undefined): string {
  const details = run?.details ?? {};
  const stage = textValue(details.stage);
  if (stage && SYNC_STAGE_LABELS[stage]) return SYNC_STAGE_LABELS[stage];
  return (
    textValue(details.stage_label) ??
    textValue(details.message) ??
    syncStatusLabel(run?.status)
  );
}

function syncDetailLine(run: SyncRun): string {
  const details = run.details ?? {};
  const pieces: string[] = [];
  const dateFrom =
    textValue(details.dateFrom) ?? textValue(details.backfill_from);
  const dateTo = textValue(details.dateTo) ?? textValue(details.backfill_to);
  const waitSeconds = numericValue(details.waitSeconds);
  const pages =
    numericValue(details.detailsPagesLoaded) ??
    numericValue(details.pagesLoaded);
  const rows =
    numericValue(details.detailsRowsLoaded) ??
    numericValue(details.rowsLoaded) ??
    numericValue(details.acquiringRows);
  const nextRrdId = numericValue(details.nextRrdId);
  if (dateFrom && dateTo) pieces.push(`${dateFrom} - ${dateTo}`);
  if (pages != null) pieces.push(`страниц: ${formatNumber(pages)}`);
  if (rows != null) pieces.push(`строк: ${formatNumber(rows)}`);
  if (nextRrdId != null)
    pieces.push(`следующий маркер: ${formatNumber(nextRrdId)}`);
  if (waitSeconds != null)
    pieces.push(`ожидание Вайлдберриз: ${formatNumber(waitSeconds)} сек.`);
  return pieces.join(" · ");
}

function latestRun(runs: SyncRun[]): SyncRun | null {
  const sorted = [...runs].sort((a, b) => {
    const left = toTs(a.started_at) || toTs(a.finished_at);
    const right = toTs(b.started_at) || toTs(b.finished_at);
    return right - left;
  });
  return sorted.find(isActiveSyncRun) ?? sorted[0] ?? null;
}

function freshnessState(cursor: SyncCursor | undefined): FreshnessState {
  const status = String(cursor?.status ?? "").toLowerCase();
  if (status.includes("error") || status.includes("fail")) return "error";
  if (!cursor?.last_synced_at) return "missing";
  const ageHours = (Date.now() - toTs(cursor.last_synced_at)) / 3_600_000;
  return ageHours > 24 ? "warn" : "ok";
}

function pickFreshness(cursors: SyncCursor[]): FreshnessItem[] {
  return DOMAINS.map((cfg) => {
    const matched = cursors
      .filter((cursor) => {
        const hay =
          `${cursor.domain ?? ""} ${cursor.cursor_key ?? ""}`.toLowerCase();
        return cfg.match.some((needle) => hay.includes(needle));
      })
      .sort((a, b) => toTs(b.last_synced_at) - toTs(a.last_synced_at));
    const best = matched[0];
    return {
      key: cfg.key,
      label: cfg.label,
      Icon: cfg.Icon,
      lastSyncedAt: best?.last_synced_at ?? null,
      status: best?.status ?? null,
      source: best
        ? [best.domain, best.cursor_key].filter(Boolean).join(" / ")
        : null,
      state: freshnessState(best),
    };
  });
}

function iconTone(state: FreshnessState): string {
  switch (state) {
    case "ok":
      return "border-success/30 bg-success/10 text-success";
    case "warn":
      return "border-warning/40 bg-warning/10 text-warning";
    case "error":
      return "border-destructive/35 bg-destructive/10 text-destructive";
    case "missing":
      return "border-border bg-muted/45 text-muted-foreground";
  }
}

function dotTone(state: FreshnessState): string {
  switch (state) {
    case "ok":
      return "bg-success";
    case "warn":
      return "bg-warning";
    case "error":
      return "bg-destructive";
    case "missing":
      return "bg-muted-foreground/50";
  }
}

function badgeTone(hasActiveRun: boolean, issues: number): string {
  if (hasActiveRun) return "border-primary/30 bg-primary/10 text-primary";
  if (issues > 0) return "border-warning/40 bg-warning/10 text-warning";
  return "border-success/30 bg-success/10 text-success";
}

function cleanTechnicalCopy(value: string | null | undefined): string {
  return String(value ?? "")
    .replace(/WB API request failed:?/gi, "Запрос к Вайлдберриз не прошел.")
    .replace(/\bWB\b/g, "Вайлдберриз")
    .replace(/\bAPI\b/g, "интерфейс");
}

export function TopBarSyncStatus({ accountId }: { accountId: number | null }) {
  const cursorsQ = useQuery({
    queryKey: ["topbar-sync-cursors", accountId],
    enabled: !!accountId,
    queryFn: () =>
      apiList<SyncCursor>(API_ENDPOINTS.sync.cursors, {
        query: { account_id: accountId!, limit: 200 },
      }),
    staleTime: 60_000,
  });

  const runsQ = useQuery({
    queryKey: ["topbar-sync-runs", accountId],
    enabled: !!accountId,
    queryFn: () =>
      apiList<SyncRun>(API_ENDPOINTS.sync.runs, {
        query: { account_id: accountId!, limit: 12, offset: 0 },
      }),
    staleTime: 0,
    retry: false,
    refetchInterval: (query) => {
      const runs = (query.state.data as SyncRun[] | undefined) ?? [];
      return runs.some(isActiveSyncRun) ? 2_000 : 30_000;
    },
  });

  const freshness = useMemo(
    () => pickFreshness(cursorsQ.data ?? []),
    [cursorsQ.data],
  );
  const run = useMemo(() => latestRun(runsQ.data ?? []), [runsQ.data]);
  const active = isActiveSyncRun(run);
  const percent = active ? syncProgressPercent(run) : 100;
  const issues = freshness.filter((item) => item.state !== "ok").length;
  const healthy = freshness.length - issues;
  const ringPercent = active
    ? percent
    : Math.round((healthy / Math.max(freshness.length, 1)) * 100);
  const ringColor = active
    ? "var(--primary)"
    : issues
      ? "var(--warning)"
      : "var(--success)";
  const detailLine = run ? syncDetailLine(run) : "";
  const stage = run ? syncStageLabel(run) : null;
  const loading = cursorsQ.isLoading || runsQ.isLoading;

  if (!accountId) return null;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="h-9 gap-1.5 rounded-lg border-border/70 bg-background px-1.5 shadow-sm shadow-black/[0.025] hover:bg-accent sm:h-10 sm:px-2"
          title="Статус синхронизации"
        >
          <span className="hidden items-center gap-1 xl:flex">
            {freshness.map((item) => (
              <span
                key={item.key}
                className={cn(
                  "relative flex h-7 w-7 items-center justify-center rounded-md border",
                  iconTone(item.state),
                )}
                title={`${item.label}: ${formatSyncTime(item.lastSyncedAt)}`}
              >
                <item.Icon className="h-3.5 w-3.5" />
                <span
                  className={cn(
                    "absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full ring-2 ring-background",
                    dotTone(item.state),
                  )}
                />
              </span>
            ))}
          </span>
          <span
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full p-[2px]"
            style={{
              background: `conic-gradient(${ringColor} ${ringPercent * 3.6}deg, var(--muted) 0deg)`,
            }}
          >
            <span className="flex h-full w-full items-center justify-center rounded-full bg-background">
              {loading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
              ) : active ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin text-primary" />
              ) : issues ? (
                <AlertTriangle className="h-3.5 w-3.5 text-warning" />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5 text-success" />
              )}
            </span>
          </span>
          <span className="hidden min-w-8 text-xs font-semibold tabular-nums sm:inline">
            {active ? `${percent}%` : `${healthy}/${freshness.length}`}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-[calc(100vw-2rem)] max-w-[390px] rounded-xl p-3"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <DatabaseZap className="h-4 w-4 text-primary" />
              Синхронизация
            </div>
            <div className="mt-0.5 truncate text-xs text-muted-foreground">
              {active
                ? `${domainLabel(run?.domain ?? "")}: ${stage}`
                : issues
                  ? "Есть источники, которые нужно проверить"
                  : "Основные источники свежие"}
            </div>
          </div>
          <Badge
            variant="outline"
            className={cn(
              "h-6 shrink-0 rounded-md px-2 text-[11px] font-medium",
              badgeTone(active, issues),
            )}
          >
            {active ? "идет" : issues ? "внимание" : "готово"}
          </Badge>
        </div>

        {run ? (
          <div className="mt-3 rounded-lg border border-border/70 bg-muted/25 p-3">
            <div className="flex items-center justify-between gap-2 text-xs">
              <div className="min-w-0">
                <div className="truncate font-medium text-foreground">
                  {domainLabel(run.domain)}
                </div>
                <div className="truncate text-muted-foreground">
                  #{run.id} · {syncStatusLabel(run.status)}
                </div>
              </div>
              <div className="shrink-0 text-sm font-semibold tabular-nums text-foreground">
                {syncProgressPercent(run)}%
              </div>
            </div>
            <Progress value={syncProgressPercent(run)} className="mt-2 h-1.5" />
            <div className="mt-2 text-xs font-medium text-foreground">
              {syncStageLabel(run)}
            </div>
            {detailLine ? (
              <div className="mt-1 text-[11px] leading-4 text-muted-foreground">
                {detailLine}
              </div>
            ) : null}
            {run.error_text ? (
              <div className="mt-1 text-[11px] leading-4 text-destructive">
                {cleanTechnicalCopy(run.error_text)}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="mt-3 grid grid-cols-5 gap-1.5">
          {freshness.map((item) => (
            <div
              key={item.key}
              className="min-w-0 rounded-lg border border-border/70 bg-background p-2 text-center"
              title={item.source ?? "Источник синхронизации не найден"}
            >
              <div
                className={cn(
                  "mx-auto flex h-8 w-8 items-center justify-center rounded-md border",
                  iconTone(item.state),
                )}
              >
                <item.Icon className="h-4 w-4" />
              </div>
              <div className="mt-1 truncate text-[10px] font-medium leading-3 text-foreground">
                {item.label}
              </div>
              <div className="mt-0.5 truncate text-[10px] leading-3 text-muted-foreground">
                {formatSyncTime(item.lastSyncedAt)}
              </div>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
