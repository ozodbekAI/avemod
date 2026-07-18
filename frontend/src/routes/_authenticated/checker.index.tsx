// @ts-nocheck
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUpDown,
  Bot,
  Camera,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  FileText,
  ImageOff,
  ListChecks,
  Loader2,
  MoreVertical,
  RefreshCw,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Sparkles,
  TableProperties,
} from "lucide-react";
import { toast } from "sonner";
import { useAccounts } from "@/lib/account-context";
import {
  analyzeAccountCardQuality,
  fetchCardQualityFixedFileStatus,
  fetchCardQualityProducts,
  fetchCardQualityQueueProgress,
  type CardQualityProductRow,
} from "@/lib/portal";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { EndpointError } from "@/components/EndpointError";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_authenticated/checker/")({
  component: CheckerCardsPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

type SortKey =
  | "quality_issues"
  | "critical_issues"
  | "quality_score"
  | "status"
  | "analyzed_at"
  | "updated_at"
  | "title";
type SortDir = "asc" | "desc";

const PAGE_SIZE = 50;

function numberText(value: number | null | undefined) {
  return Number(value ?? 0).toLocaleString("ru-RU");
}

function asNumber(value: unknown, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function text(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function normalize(value: unknown): string {
  return text(value).trim().toLowerCase();
}

function productTitle(row: CardQualityProductRow) {
  return row.title || row.vendor_code || `Товар ${row.nm_id}`;
}

function statusLabel(status?: string | null, issueCount = 0) {
  const key = normalize(status);
  if (issueCount > 0 && (key === "critical" || key === "warning")) {
    return key === "critical" ? "Требует исправления" : "Есть замечания";
  }
  const map: Record<string, string> = {
    ok: "Прошла проверку",
    clean: "Прошла проверку",
    critical: "Критично",
    warning: "Есть замечания",
    not_analyzed: "Не проверена",
    empty: "Нет карточки",
    unavailable: "Недоступно",
  };
  return map[key] ?? (issueCount > 0 ? "Требует исправления" : "Не проверена");
}

function statusClass(status?: string | null, issueCount = 0) {
  const key = normalize(status);
  if (issueCount > 0 || key === "critical") {
    return "border-destructive/30 bg-destructive/10 text-destructive";
  }
  if (key === "warning") {
    return "border-warning/30 bg-warning/10 text-warning";
  }
  if (key === "ok" || key === "clean") {
    return "border-success/30 bg-success/10 text-success";
  }
  return "border-border bg-muted text-muted-foreground";
}

function scoreTone(score?: number | null) {
  if (score == null) return "text-muted-foreground";
  if (score < 50) return "text-destructive";
  if (score < 75) return "text-warning";
  return "text-success";
}

function scoreProgressClass(score?: number | null) {
  if (score == null) return "[&>div]:bg-muted-foreground";
  if (score < 50) return "[&>div]:bg-destructive";
  if (score < 75) return "[&>div]:bg-warning";
  return "[&>div]:bg-success";
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function CheckerCardsPage() {
  const { activeId } = useAccounts();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [qualityStatus, setQualityStatus] = useState("all");
  const [scoreFilter, setScoreFilter] = useState("all");
  const [aiFilter, setAiFilter] = useState("all");
  const [mediaFilter, setMediaFilter] = useState("all");
  const [sortBy, setSortBy] = useState<SortKey>("quality_issues");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [offset, setOffset] = useState(0);
  const debounced = useDebouncedValue(search.trim(), 250);

  const query = useQuery({
    queryKey: [
      "checker-products",
      activeId,
      debounced,
      qualityStatus,
      scoreFilter,
      aiFilter,
      mediaFilter,
      sortBy,
      sortDir,
      offset,
    ],
    enabled: !!activeId,
    queryFn: () =>
      fetchCardQualityProducts(activeId, {
        limit: PAGE_SIZE,
        offset,
        ...(debounced ? { search: debounced } : {}),
        ...(qualityStatus !== "all" ? { quality_status: qualityStatus } : {}),
        ...(scoreFilter !== "all" ? { score_filter: scoreFilter } : {}),
        ...(aiFilter !== "all" ? { ai_filter: aiFilter } : {}),
        ...(mediaFilter !== "all" ? { media_filter: mediaFilter } : {}),
        sort_by: sortBy,
        sort_dir: sortDir,
      }),
    staleTime: 30_000,
  });

  const fixedFile = useQuery({
    queryKey: ["checker-fixed-file-status", activeId],
    enabled: !!activeId,
    queryFn: () => fetchCardQualityFixedFileStatus(activeId),
    staleTime: 60_000,
  });

  const queue = useQuery({
    queryKey: ["checker-queue-progress", activeId],
    enabled: !!activeId,
    queryFn: () => fetchCardQualityQueueProgress(activeId, { bucket: "all" }),
    staleTime: 30_000,
  });

  const analyzeMutation = useMutation({
    mutationFn: (force: boolean) =>
      analyzeAccountCardQuality(activeId, { force, limit: 200 }),
    onSuccess: (result: any) => {
      toast.success(
        result?.status === "already_running"
          ? "Проверка уже запущена"
          : "Проверка карточек запущена",
      );
      queryClient.invalidateQueries({ queryKey: ["checker-products"] });
      queryClient.invalidateQueries({ queryKey: ["checker-queue-progress"] });
      queryClient.invalidateQueries({ queryKey: ["portal-actions"] });
      queryClient.invalidateQueries({ queryKey: ["portal-product-detail"] });
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось запустить checker"),
  });

  const rows = query.data?.items ?? [];
  const summary = query.data?.summary ?? {};
  const total = asNumber(query.data?.total ?? summary.total_cards);
  const analyzed = asNumber(summary.analyzed_cards);
  const withIssues = asNumber(summary.cards_with_issues);
  const critical = asNumber(summary.critical_cards);
  const clean = asNumber(summary.clean_cards);
  const notAnalyzed = asNumber(summary.not_analyzed_cards);
  const averageScore = summary.average_score;
  const pending = asNumber(queue.data?.pending);
  const fixed = asNumber(queue.data?.fixed);
  const queueTotal = asNumber(queue.data?.total);

  const stats = useMemo(
    () => [
      {
        label: "Все карточки",
        value: total,
        icon: ListChecks,
        tone: "primary",
      },
      {
        label: "С проблемами",
        value: withIssues,
        icon: CircleAlert,
        tone: "warning",
      },
      {
        label: "Критично",
        value: critical,
        icon: CircleAlert,
        tone: "danger",
      },
      {
        label: "Прошли",
        value: clean,
        icon: CheckCircle2,
        tone: "success",
      },
      {
        label: "Не проверены",
        value: notAnalyzed,
        icon: Clock3,
        tone: "muted",
      },
      {
        label: "Средний score",
        value: averageScore == null ? "—" : Math.round(Number(averageScore)),
        icon: Sparkles,
        tone: "primary",
      },
    ],
    [averageScore, clean, critical, notAnalyzed, total, withIssues],
  );

  function resetFilters() {
    setSearch("");
    setQualityStatus("all");
    setScoreFilter("all");
    setAiFilter("all");
    setMediaFilter("all");
    setSortBy("quality_issues");
    setSortDir("desc");
    setOffset(0);
  }

  if (!activeId) {
    return (
      <PageShell>
        <PageHeader title="Проверка карточек" />
        <NoAccountSelected message="Выберите WB-аккаунт в верхней панели, чтобы открыть checker." />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="Проверка карточек"
        description="Реальный checker из backend: анализ WB-карточек, AI-рекомендации, diff, локальная фиксация и отправка в WB по capability."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
            >
              <RefreshCw
                className={cn("h-4 w-4", query.isFetching && "animate-spin")}
              />
              Обновить
            </Button>
            <Button asChild variant="outline">
              <Link to="/checker/fixed-file">
                <TableProperties className="h-4 w-4" />
                {fixedFile.data?.has_fixed_file
                  ? `Fixed file ${numberText(fixedFile.data.total)}`
                  : "Fixed file"}
              </Link>
            </Button>
            <Button
              variant="outline"
              onClick={() => analyzeMutation.mutate(false)}
              disabled={analyzeMutation.isPending}
            >
              {analyzeMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Сверить с WB
            </Button>
            <Button
              onClick={() => analyzeMutation.mutate(true)}
              disabled={analyzeMutation.isPending}
            >
              <RotateCcw className="h-4 w-4" />
              Заново
            </Button>
          </>
        }
      />

      <div className="mb-4 grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        {stats.map((item) => {
          const Icon = item.icon;
          return (
            <Card key={item.label} className="overflow-hidden">
              <CardContent className="flex items-center gap-3 p-3">
                <div
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-md border",
                    item.tone === "danger" &&
                      "border-destructive/30 bg-destructive/10 text-destructive",
                    item.tone === "warning" &&
                      "border-warning/30 bg-warning/10 text-warning",
                    item.tone === "success" &&
                      "border-success/30 bg-success/10 text-success",
                    item.tone === "primary" &&
                      "border-primary/30 bg-primary/10 text-primary",
                    item.tone === "muted" &&
                      "border-border bg-muted text-muted-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-xs text-muted-foreground">
                    {item.label}
                  </div>
                  <div className="text-lg font-semibold tabular-nums">
                    {typeof item.value === "number"
                      ? numberText(item.value)
                      : item.value}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card className="mb-4">
        <CardContent className="space-y-3 p-3">
          <div className="grid gap-2 lg:grid-cols-[minmax(240px,1fr)_160px_160px_160px_160px_190px_120px]">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setOffset(0);
                }}
                placeholder="Поиск: nmID, артикул, бренд, название"
                className="pl-9"
              />
            </div>
            <FilterSelect value={qualityStatus} onChange={setQualityStatus}>
              <SelectItem value="all">Все статусы</SelectItem>
              <SelectItem value="issues">С ошибками</SelectItem>
              <SelectItem value="critical">Критичные</SelectItem>
              <SelectItem value="ok">Прошли</SelectItem>
              <SelectItem value="not_analyzed">Не проверены</SelectItem>
            </FilterSelect>
            <FilterSelect value={scoreFilter} onChange={setScoreFilter}>
              <SelectItem value="all">Любой score</SelectItem>
              <SelectItem value="critical">0-49</SelectItem>
              <SelectItem value="warning">50-74</SelectItem>
              <SelectItem value="good">75+</SelectItem>
              <SelectItem value="no_score">Нет score</SelectItem>
            </FilterSelect>
            <FilterSelect value={aiFilter} onChange={setAiFilter}>
              <SelectItem value="all">Любой AI</SelectItem>
              <SelectItem value="has_ai">Есть AI</SelectItem>
              <SelectItem value="no_ai">Без AI</SelectItem>
              <SelectItem value="hidden_no_fix">AI без fix</SelectItem>
            </FilterSelect>
            <FilterSelect value={mediaFilter} onChange={setMediaFilter}>
              <SelectItem value="all">Любое медиа</SelectItem>
              <SelectItem value="few_photos">Мало фото</SelectItem>
              <SelectItem value="no_video">Нет видео</SelectItem>
              <SelectItem value="has_video">Есть видео</SelectItem>
            </FilterSelect>
            <FilterSelect value={sortBy} onChange={setSortBy}>
              <SelectItem value="quality_issues">Сначала проблемы</SelectItem>
              <SelectItem value="critical_issues">По критичным</SelectItem>
              <SelectItem value="quality_score">По score</SelectItem>
              <SelectItem value="status">По статусу</SelectItem>
              <SelectItem value="analyzed_at">По проверке</SelectItem>
              <SelectItem value="updated_at">По обновлению WB</SelectItem>
              <SelectItem value="title">По названию</SelectItem>
            </FilterSelect>
            <Button
              variant="outline"
              onClick={() => setSortDir((v) => (v === "desc" ? "asc" : "desc"))}
            >
              <ArrowUpDown className="h-4 w-4" />
              {sortDir === "desc" ? "DESC" : "ASC"}
            </Button>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <span>Найдено: {numberText(total)}</span>
              <span>· показано: {numberText(rows.length)}</span>
              <span>
                · queue: {numberText(fixed)}/{numberText(queueTotal)}
              </span>
              {fixedFile.data?.has_fixed_file ? (
                <Badge variant="outline" className="text-[11px]">
                  fixed-file: {numberText(fixedFile.data.total)}
                </Badge>
              ) : null}
              {pending > 0 ? (
                <Badge variant="outline" className="text-[11px]">
                  pending: {numberText(pending)}
                </Badge>
              ) : null}
            </div>
            <Button variant="ghost" size="sm" onClick={resetFilters}>
              <SlidersHorizontal className="h-3.5 w-3.5" />
              Сбросить фильтры
            </Button>
          </div>
        </CardContent>
      </Card>

      {query.isError ? (
        <Alert className="mb-4 border-destructive/40">
          <CircleAlert className="h-4 w-4" />
          <AlertTitle>Checker data не загрузилась</AlertTitle>
          <AlertDescription>
            {query.error?.message ??
              "Проверьте backend endpoint /portal/card-quality/products."}
          </AlertDescription>
        </Alert>
      ) : null}

      {query.isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-[118px] rounded-lg" />
          ))}
        </div>
      ) : rows.length > 0 ? (
        <div className="space-y-3">
          {rows.map((row) => (
            <ProductQualityRow
              key={`${row.account_id}:${row.nm_id}`}
              row={row}
            />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex min-h-[220px] flex-col items-center justify-center gap-3 p-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg border bg-muted text-muted-foreground">
              <ListChecks className="h-6 w-6" />
            </div>
            <div>
              <div className="font-semibold">
                Карточки по фильтру не найдены
              </div>
              <div className="mt-1 max-w-md text-sm text-muted-foreground">
                Если checker ещё не запускался, нажмите «Сверить с WB» или
                сбросьте фильтры.
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={resetFilters}>
                Сбросить
              </Button>
              <Button onClick={() => analyzeMutation.mutate(false)}>
                <RefreshCw className="h-4 w-4" />
                Сверить с WB
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="mt-4 flex items-center justify-between">
        <Button
          variant="outline"
          disabled={offset === 0 || query.isFetching}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          <ChevronLeft className="h-4 w-4" />
          Назад
        </Button>
        <div className="text-xs text-muted-foreground">
          {numberText(offset + 1)}-{numberText(offset + rows.length)} из{" "}
          {numberText(total)}
        </div>
        <Button
          variant="outline"
          disabled={offset + PAGE_SIZE >= total || query.isFetching}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Далее
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </PageShell>
  );
}

function FilterSelect({
  value,
  onChange,
  children,
}: {
  value: string;
  onChange: (value: any) => void;
  children: React.ReactNode;
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v)}>
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>{children}</SelectContent>
    </Select>
  );
}

function ProductQualityRow({ row }: { row: CardQualityProductRow }) {
  const score = typeof row.score === "number" ? row.score : null;
  const issueCount = asNumber(row.issue_count);
  const critical = asNumber(row.critical_issue_count);
  const warning = asNumber(row.warning_issue_count);
  const ai = asNumber(row.ai_issue_count);
  const photos = asNumber(row.photos_count);
  const videos = asNumber(row.video_count);
  const mediaTotal = photos + videos;
  const actionable = asNumber(row.actionable_issue_count);
  const growth =
    score == null
      ? null
      : Math.min(100 - score, Math.max(0, actionable + ai + critical));

  return (
    <Link
      to="/checker/$nmId"
      params={{ nmId: String(row.nm_id) }}
      className="block overflow-hidden rounded-lg border bg-card text-card-foreground transition-colors hover:border-primary/40 hover:bg-accent/30"
    >
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(260px,1.55fr)_360px_130px_220px_32px] lg:items-center">
        <div className="flex min-w-0 items-center gap-3">
          <ProductThumb src={row.thumbnail_url} title={productTitle(row)} />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">
              {productTitle(row)}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
              <span>{row.nm_id}</span>
              {row.vendor_code ? (
                <>
                  <span>·</span>
                  <span>{row.vendor_code}</span>
                </>
              ) : null}
              {row.subject_name ? (
                <>
                  <span>·</span>
                  <span>{row.subject_name}</span>
                </>
              ) : null}
            </div>
          </div>
        </div>

        <QualitySignal row={row} />

        <div className="text-center">
          <div className="flex items-baseline gap-1">
            <span
              className={cn(
                "text-3xl font-bold tabular-nums",
                scoreTone(score),
              )}
            >
              {score ?? "—"}
            </span>
            <span className="text-sm text-muted-foreground">/</span>
            <span className="text-sm text-muted-foreground">100</span>
          </div>
          {growth != null ? (
            <div className="mt-1 text-xs font-semibold text-success">
              +{growth}
            </div>
          ) : null}
        </div>

        <div className="text-center text-xs">
          <div
            className={cn(
              "inline-flex items-center gap-1 font-medium",
              issueCount > 0 ? "text-destructive" : "text-success",
            )}
          >
            <CircleAlert className="h-3.5 w-3.5" />
            {statusLabel(row.status, issueCount)}
          </div>
          <div className="mt-2 font-semibold tabular-nums text-muted-foreground">
            {issueCount} ошибок
          </div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            {actionable} actionable / {mediaTotal} media
          </div>
        </div>

        <MoreVertical className="hidden h-5 w-5 text-muted-foreground lg:block" />
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-dashed px-4 py-2 text-xs text-muted-foreground">
        <div className="flex min-w-0 items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">
            Глубокий AI-анализ медиаконтента · Проверка фото и видео на
            соответствие требованиям WB
          </span>
        </div>
        <span className="hidden shrink-0 md:inline">Запустить · 1 кредит</span>
      </div>
    </Link>
  );
}

function ProductThumb({ src, title }: { src?: string | null; title: string }) {
  return (
    <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
      {src ? (
        <img
          src={src}
          alt={title}
          loading="lazy"
          className="h-full w-full object-cover"
        />
      ) : (
        <ImageOff className="h-5 w-5 text-muted-foreground" />
      )}
    </div>
  );
}

function QualitySignal({ row }: { row: CardQualityProductRow }) {
  const top = normalize(row.top_issue_category);
  const issueCount = asNumber(row.issue_count);
  const critical = asNumber(row.critical_issue_count);
  const ai = asNumber(row.ai_issue_count);
  const values = [
    {
      label: "Хар-ки",
      active: top.includes("character") || top.includes("характер"),
      level: critical ? "danger" : issueCount ? "warning" : "ok",
      height: 30,
    },
    {
      label: "Title",
      active: top.includes("title"),
      level: top.includes("title") ? "danger" : issueCount ? "warning" : "ok",
      height: 26,
    },
    {
      label: "Desc",
      active: top.includes("description"),
      level: top.includes("description")
        ? "danger"
        : issueCount
          ? "warning"
          : "ok",
      height: 24,
    },
    {
      label: "Фото",
      active: asNumber(row.photos_count) < 3,
      level: asNumber(row.photos_count) < 3 ? "warning" : "ok",
      height: 18,
    },
    {
      label: "Видео",
      active: asNumber(row.video_count) === 0,
      level: asNumber(row.video_count) === 0 ? "muted" : "ok",
      height: 16,
    },
    {
      label: "Ракурс",
      active: false,
      level: "muted",
      height: 18,
    },
    {
      label: "Cons",
      active: ai === 0 && issueCount === 0,
      level: issueCount > 0 ? "ok" : "ok",
      height: 40,
    },
  ];

  return (
    <div className="flex items-end gap-3">
      {values.map((item) => (
        <div key={item.label} className="flex w-8 flex-col items-center">
          <div
            className={cn(
              "w-3 rounded-full",
              item.level === "danger" && "bg-destructive",
              item.level === "warning" && "bg-warning",
              item.level === "ok" && "bg-success",
              item.level === "primary" && "bg-primary",
              item.level === "muted" && "bg-muted",
              item.active && "ring-2 ring-offset-2",
            )}
            style={{ height: item.height }}
          />
          <div className="mt-1 truncate text-[10px] text-muted-foreground">
            {item.label}
          </div>
        </div>
      ))}
    </div>
  );
}
