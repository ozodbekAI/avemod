// @ts-nocheck
import { createFileRoute, Link } from "@tanstack/react-router";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useAccounts } from "@/lib/account-context";
import { useDateRange } from "@/lib/date-range-context";
import {
  fetchPortalProducts,
  type PortalProductRow,
  type PortalProductsPage,
} from "@/lib/portal";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { PageShell } from "@/components/PageShell";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { EndpointError } from "@/components/EndpointError";
import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpDown,
  Boxes,
  Camera,
  Copy,
  ImageOff,
  ListChecks,
  PackageOpen,
  Search,
  Star,
} from "lucide-react";
import { formatMoney } from "@/lib/format";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/products/")({
  component: ProductsPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

const STATUS_COLORS: Record<string, string> = {
  ok: "border-success/25 bg-success/10 text-success",
  healthy:
    "border-success/25 bg-success/10 text-success",
  trusted:
    "border-success/25 bg-success/10 text-success",
  financial_final:
    "border-success/25 bg-success/10 text-success",
  complete:
    "border-success/25 bg-success/10 text-success",
  done: "border-success/25 bg-success/10 text-success",
  resolved:
    "border-success/25 bg-success/10 text-success",

  warning:
    "border-warning/30 bg-warning/10 text-warning",
  risk: "border-warning/30 bg-warning/10 text-warning",
  degraded:
    "border-warning/30 bg-warning/10 text-warning",
  running:
    "border-warning/30 bg-warning/10 text-warning",
  stale:
    "border-warning/30 bg-warning/10 text-warning",
  syncing:
    "border-warning/30 bg-warning/10 text-warning",
  provisional:
    "border-warning/30 bg-warning/10 text-warning",
  operational_provisional:
    "border-warning/30 bg-warning/10 text-warning",
  test_only:
    "border-warning/30 bg-warning/10 text-warning",
  low_stock:
    "border-warning/30 bg-warning/10 text-warning",
  overstock:
    "border-warning/30 bg-warning/10 text-warning",
  partial:
    "border-warning/30 bg-warning/10 text-warning",
  in_progress:
    "border-warning/30 bg-warning/10 text-warning",
  postponed:
    "border-warning/30 bg-warning/10 text-warning",

  critical:
    "border-destructive/30 bg-destructive/10 text-destructive",
  bad: "border-destructive/30 bg-destructive/10 text-destructive",
  blocked:
    "border-destructive/30 bg-destructive/10 text-destructive",
  data_blocked:
    "border-destructive/30 bg-destructive/10 text-destructive",
  error:
    "border-destructive/30 bg-destructive/10 text-destructive",
  failed:
    "border-destructive/30 bg-destructive/10 text-destructive",
  missing:
    "border-destructive/30 bg-destructive/10 text-destructive",

  not_analyzed: "border-border bg-muted text-muted-foreground",
  not_configured: "border-border bg-muted text-muted-foreground",
  unavailable: "border-border bg-muted text-muted-foreground",
  disabled: "border-border bg-muted text-muted-foreground",
  unknown: "border-border bg-muted text-muted-foreground",
  empty: "border-border bg-muted text-muted-foreground",
  ignored: "border-border bg-muted text-muted-foreground",
};

const STATUS_LABEL_RU: Record<string, string> = {
  ok: "В порядке",
  healthy: "В порядке",
  trusted: "Проверено",
  financial_final: "Финально",
  complete: "Готово",
  done: "Готово",
  resolved: "Решено",
  warning: "Есть замечания",
  risk: "Риск",
  degraded: "Требует внимания",
  running: "Идёт проверка",
  stale: "Устарело",
  syncing: "Синхронизация",
  provisional: "Предварительно",
  operational_provisional: "Операционно",
  test_only: "Тестовые данные",
  low_stock: "Мало остатков",
  overstock: "Перезапас",
  partial: "Частично",
  in_progress: "В работе",
  postponed: "Отложено",
  critical: "Критично",
  bad: "Плохо",
  blocked: "Заблокировано",
  data_blocked: "Данные заблокированы",
  error: "Ошибка",
  failed: "Ошибка",
  missing: "Нет данных",
  not_analyzed: "Не проверено",
  not_configured: "Не настроено",
  unavailable: "Недоступно",
  disabled: "Отключено",
  unknown: "Нет данных",
  empty: "Нет данных",
  ignored: "Пропущено",
  profitable: "Прибыльный",
  loss: "Убыток",
  stock_risk: "Риск остатков",
  overstock_risk: "Перезапас",
  fix_data_first: "Сначала данные",
  watch: "Наблюдать",
};

type SortKey =
  | "revenue"
  | "profit"
  | "margin"
  | "quality_score"
  | "quality_issues"
  | null;
type SortDir = "asc" | "desc";

function extractRows(data: PortalProductsPage | undefined): PortalProductRow[] {
  return data?.items ?? [];
}

function normalizeKey(value?: string | null) {
  return String(value ?? "").trim().toLowerCase();
}

function statusLabel(value?: string | null) {
  const key = normalizeKey(value);
  if (!key) return "Нет данных";
  return STATUS_LABEL_RU[key] ?? key.replaceAll("_", " ");
}

function statusBadge(value?: string | null, className?: string) {
  const key = normalizeKey(value) || "unknown";
  const cls = STATUS_COLORS[key] ?? "border-border bg-muted text-muted-foreground";
  return (
    <Badge
      variant="outline"
      className={cn("h-5 max-w-full truncate px-1.5 text-[10px] font-medium leading-none", cls, className)}
    >
      {statusLabel(key)}
    </Badge>
  );
}

function wbBasketHost(vol: number): string {
  const ranges: Array<[number, number]> = [
    [143, 1],
    [287, 2],
    [431, 3],
    [719, 4],
    [1007, 5],
    [1061, 6],
    [1115, 7],
    [1169, 8],
    [1313, 9],
    [1601, 10],
    [1655, 11],
    [1919, 12],
    [2045, 13],
    [2189, 14],
    [2405, 15],
    [2621, 16],
    [2837, 17],
    [3053, 18],
    [3269, 19],
    [3485, 20],
    [3701, 21],
    [3917, 22],
    [4133, 23],
    [4349, 24],
    [4565, 25],
    [4877, 26],
    [5193, 27],
    [5509, 28],
    [5825, 29],
    [6141, 30],
  ];
  const basket = ranges.find(([maxVol]) => vol <= maxVol)?.[1] ?? 30;
  return `basket-${String(basket).padStart(2, "0")}.wbbasket.ru`;
}

function wbImageCandidates(nmId: string | number): string[] {
  const n = Number(nmId);
  if (!Number.isFinite(n) || n <= 0) return [];
  const vol = Math.floor(n / 100000);
  const part = Math.floor(n / 1000);
  const host = wbBasketHost(vol);
  return [
    `https://${host}/vol${vol}/part${part}/${n}/images/c246x328/1.webp`,
  ];
}

function proxyWbImageUrl(src: string | null): string | null {
  if (!src) return null;
  return src;
}

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function firstArrayImage(value: unknown): string | null {
  if (!Array.isArray(value)) return null;
  for (const item of value) {
    if (typeof item === "string" && item.trim()) return item.trim();
    if (item && typeof item === "object") {
      const url = firstString(
        (item as any).big,
        (item as any).canonical_url,
        (item as any).url,
        (item as any).full,
        (item as any).photo,
        (item as any).source_url,
        (item as any).src,
        (item as any).c516x688,
        (item as any).square,
        (item as any).c246x328,
        (item as any).tm,
        (item as any).thumbnail,
        (item as any).preview,
      );
      if (url) return url;
    }
  }
  return null;
}

function productImage(row: PortalProductRow): string | null {
  return firstString(
    (row as any).thumbnail,
    (row as any).thumbnail_url,
    (row as any).display_photo_url,
    (row as any).proxy_photo_url,
    row.main_photo_url,
    row.image_url,
    row.photo_url,
    row.photo,
    firstArrayImage((row as any).photos),
    firstArrayImage((row as any).images),
    firstArrayImage((row as any).raw?.photos),
    firstArrayImage((row as any).raw?.identity?.photos),
  );
}

function ProductImage({
  row,
  alt,
}: {
  row: PortalProductRow;
  alt: string;
}) {
  const primary = productImage(row) ?? wbImageCandidates(row.nm_id)[0] ?? null;
  const displayUrl = proxyWbImageUrl(primary);
  const candidates = displayUrl ? [displayUrl] : [];
  const [idx, setIdx] = useState(0);

  if (!candidates.length || idx >= candidates.length) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-1 bg-muted text-muted-foreground">
        <ImageOff className="h-5 w-5" />
        <span className="text-[10px] font-medium">Нет фото</span>
      </div>
    );
  }

  return (
    <img
      key={candidates[idx]}
      src={candidates[idx]}
      alt={alt}
      loading="lazy"
      referrerPolicy="no-referrer"
      className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
      onError={() => setIdx((i) => i + 1)}
    />
  );
}

function productTitle(row: PortalProductRow) {
  return row.name || row.title || row.vendor_code || `Товар ${row.nm_id}`;
}

function formatMargin(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "не рассчитано";
  const normalized = value <= 1 && value >= -1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

async function copyProductValue(
  event: React.MouseEvent | React.KeyboardEvent,
  label: string,
  value: string | number | null | undefined,
) {
  event.preventDefault();
  event.stopPropagation();
  const text = String(value ?? "").trim();
  if (!text) return;

  try {
    await navigator.clipboard.writeText(text);
    toast.success(`${label} скопирован`);
  } catch {
    toast.error("Не удалось скопировать");
  }
}

function CopyToken({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  if (value == null || value === "") return null;
  return (
    <span
      role="button"
      tabIndex={0}
      title={`Скопировать ${label}`}
      className="inline-flex shrink-0 items-center gap-1 rounded border bg-background px-1.5 py-0.5 font-mono text-[11px] leading-4 text-foreground transition-colors hover:border-primary/45 hover:bg-primary/10"
      onClick={(event) => copyProductValue(event, label, value)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          copyProductValue(event, label, value);
        }
      }}
    >
      <span className="text-muted-foreground">{label}:</span>
      <span>{value}</span>
      <Copy className="h-3 w-3 text-muted-foreground" />
    </span>
  );
}

function SortButton({
  label,
  sortId,
  sortKey,
  sortDir,
  onClick,
}: {
  label: string;
  sortId: Exclude<SortKey, null>;
  sortKey: SortKey;
  sortDir: SortDir;
  onClick: () => void;
}) {
  const active = sortKey === sortId;
  const Icon = !active ? ArrowUpDown : sortDir === "desc" ? ArrowDown : ArrowUp;
  return (
    <Button
      type="button"
      size="sm"
      variant={active ? "default" : "outline"}
      className={cn(
        "h-7 px-2 text-[11px]",
        active && "bg-primary text-primary-foreground hover:bg-primary/90",
      )}
      onClick={onClick}
    >
      <Icon className="h-3 w-3" />
      {label}
    </Button>
  );
}

function CompactMetric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "danger";
}) {
  return (
    <div className="min-w-0">
      <div className="truncate text-[11px] leading-4 text-muted-foreground">{label}</div>
      <div
        className={cn(
          "truncate text-sm font-semibold leading-5 tabular-nums text-foreground",
          tone === "danger" && "text-destructive",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function ProductCard({ row }: { row: PortalProductRow }) {
  const nmId = row.nm_id;
  const title = productTitle(row);
  const revenue = numberOrNull(row.revenue);
  const profit = numberOrNull(row.profit ?? row.estimated_profit);
  const margin = numberOrNull(row.margin);
  const qualityScore = numberOrNull(row.card_quality_score);
  const qualityIssues = row.card_quality_issue_count ?? 0;
  const photoCount = row.card_quality_photo_count ?? null;
  const openActions = row.open_actions_count ?? 0;
  const nextAction =
    row.next_action?.title ||
    row.top_action?.title ||
    row.next_action_title ||
    null;
  const hasProfit = profit != null;

  return (
    <Link
      to="/products/$nmId"
      params={{ nmId: String(nmId) }}
      className="group block rounded-md border bg-card text-card-foreground shadow-sm transition-colors hover:border-primary/45 hover:bg-primary/[0.025] hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="grid min-h-20 gap-3 p-2 sm:grid-cols-[56px_minmax(260px,1.7fr)_112px_112px_82px_96px_minmax(170px,0.8fr)_32px] sm:items-center lg:grid-cols-[56px_minmax(360px,2fr)_122px_122px_92px_106px_minmax(210px,0.9fr)_32px]">
        <div className="relative h-16 w-12 overflow-hidden rounded-md border bg-muted">
          <ProductImage row={row} alt={title} />
          <div className="absolute left-1 top-1 rounded bg-white/95 px-1 text-[9px] font-bold leading-3 text-primary shadow-sm dark:bg-background/95">
            WB
          </div>
          {qualityScore != null && (
            <div className="absolute bottom-1 left-1 flex items-center gap-0.5 rounded bg-white/95 px-1 text-[10px] font-bold leading-3 shadow-sm dark:bg-background/95">
              <Star className="h-2.5 w-2.5 fill-primary text-primary" />
              {Math.round(qualityScore)}
            </div>
          )}
        </div>

        <div className="min-w-0">
          <div className="flex min-w-0 items-start justify-between gap-2 sm:block">
            <div className="min-w-0">
              <h2 className="truncate text-base font-semibold leading-5 text-foreground group-hover:text-primary">
                {title}
              </h2>
              <div className="mt-1 flex min-w-0 items-center gap-1.5 overflow-hidden text-xs leading-5 text-muted-foreground">
                <CopyToken label="nm ID" value={nmId} />
                <CopyToken label="Артикул" value={row.vendor_code} />
                {row.brand ? <span className="shrink-0 truncate">{row.brand}</span> : null}
                {row.subject_name ? <span className="hidden shrink truncate lg:inline">{row.subject_name}</span> : null}
              </div>
              <div className="mt-1 flex min-w-0 items-center gap-1.5 overflow-hidden">
                {statusBadge(row.card_quality_state, "shrink-0")}
                {row.stock_state ? statusBadge(row.stock_state, "hidden shrink-0 md:inline-flex") : null}
                {row.trust_state || row.data_trust_state
                  ? statusBadge(row.trust_state || row.data_trust_state, "hidden shrink-0 xl:inline-flex")
                  : null}
              </div>
            </div>
            <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground sm:hidden">
              <ArrowRight className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px] leading-4 text-muted-foreground sm:hidden">
            <span className="inline-flex items-center gap-1 rounded border bg-background px-1.5 py-0.5">
              <Camera className="h-3.5 w-3.5" />
              {photoCount != null ? `${photoCount} фото` : "фото не проверено"}
            </span>
            <span className="inline-flex items-center gap-1 rounded border bg-background px-1.5 py-0.5">
              <ListChecks className="h-3.5 w-3.5" />
              {qualityIssues}
            </span>
            <span className="inline-flex items-center gap-1 rounded border bg-background px-1.5 py-0.5">
              <Boxes className="h-3.5 w-3.5" />
              {openActions}
            </span>
          </div>
        </div>

        <div className="hidden sm:block">
          <CompactMetric
            label="Выручка"
            value={revenue != null ? formatMoney(revenue) : "нет"}
          />
        </div>
        <div className="hidden sm:block">
          <CompactMetric
            label="Прибыль"
            value={hasProfit ? formatMoney(profit) : "нет"}
            tone={hasProfit && profit < 0 ? "danger" : "default"}
          />
        </div>
        <div className="hidden sm:block">
          <CompactMetric label="Маржа" value={formatMargin(margin)} />
        </div>
        <div className="hidden sm:block">
          <CompactMetric
            label="Остаток"
            value={
              row.stock_qty != null
                ? `${Math.round(row.stock_qty).toLocaleString("ru-RU")} шт.`
                : statusLabel(row.stock_state)
            }
          />
        </div>

        <div className="hidden min-w-0 sm:block">
          <div className="flex items-center gap-1 text-[11px] leading-4 text-muted-foreground">
            <Camera className="h-3.5 w-3.5" />
            <span>{photoCount != null ? photoCount : "?"}</span>
            <ListChecks className="ml-1 h-3.5 w-3.5" />
            <span>{qualityIssues}</span>
            <Boxes className="ml-1 h-3.5 w-3.5" />
            <span>{openActions}</span>
          </div>
          <div className="mt-1 line-clamp-2 text-xs font-medium leading-4 text-foreground">
            {nextAction || "Нет активного действия"}
          </div>
        </div>

        <span className="hidden h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground transition-colors group-hover:bg-primary/90 sm:inline-flex">
          <ArrowRight className="h-4 w-4" />
        </span>
      </div>
    </Link>
  );
}

function ProductCardSkeleton() {
  return (
    <Card className="rounded-md shadow-sm">
      <CardContent className="grid min-h-20 gap-3 p-2 sm:grid-cols-[56px_minmax(260px,1.7fr)_112px_112px_82px_96px_minmax(170px,0.8fr)_32px] sm:items-center lg:grid-cols-[56px_minmax(360px,2fr)_122px_122px_92px_106px_minmax(210px,0.9fr)_32px]">
        <Skeleton className="h-16 w-12 rounded-md" />
        <div className="min-w-0 space-y-1.5">
          <Skeleton className="h-5 w-4/5" />
          <div className="flex gap-1.5">
            <Skeleton className="h-5 w-24 rounded" />
            <Skeleton className="h-5 w-28 rounded" />
            <Skeleton className="h-5 w-16 rounded" />
          </div>
          <div className="flex gap-1.5">
            <Skeleton className="h-5 w-20 rounded" />
            <Skeleton className="h-5 w-24 rounded" />
          </div>
        </div>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="hidden h-10 rounded-md sm:block" />
        ))}
        <Skeleton className="hidden h-10 rounded-md sm:block" />
        <Skeleton className="hidden h-8 w-8 rounded-md sm:block" />
      </CardContent>
    </Card>
  );
}

function ProductsPage() {
  const { activeId } = useAccounts();
  const { from: dateFrom, to: dateTo } = useDateRange();
  const [search, setSearch] = useState("");
  const debounced = useDebouncedValue(search.trim(), 350);
  const limit = 50;
  const [sortKey, setSortKey] = useState<SortKey>(null);
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [qualityStatus, setQualityStatus] = useState("");
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  const {
    data,
    isLoading,
    error,
    refetch,
    isFetching,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: [
      "portal-products",
      activeId,
      dateFrom,
      dateTo,
      limit,
      debounced,
      qualityStatus,
      sortKey,
      sortDir,
    ],
    initialPageParam: 0,
    queryFn: ({ pageParam = 0 }) =>
      fetchPortalProducts(
        activeId,
        {
          limit,
          offset: pageParam,
          ...(debounced ? { search: debounced } : {}),
          ...(qualityStatus ? { card_quality_status: qualityStatus } : {}),
          ...(sortKey && sortKey !== "margin"
            ? { sort_by: sortKey, sort_dir: sortDir }
            : {}),
        },
        { dateFrom, dateTo },
      ),
    getNextPageParam: (lastPage) => {
      const pageItems = lastPage?.items?.length ?? 0;
      const nextOffset = (lastPage?.offset ?? 0) + pageItems;
      if (!pageItems || nextOffset >= (lastPage?.total ?? 0)) return undefined;
      return nextOffset;
    },
    enabled: !!activeId,
    staleTime: 60_000,
  });

  const pages = data?.pages ?? [];
  const rows = pages.flatMap(extractRows);
  const total = pages[0]?.total ?? rows.length;
  const loadedCount = rows.length;

  const baseFiltered = debounced
    ? rows.filter((row) => {
        const q = debounced.toLowerCase();
        return (
          String(row.nm_id).includes(q) ||
          (row.vendor_code ?? "").toLowerCase().includes(q) ||
          (row.name ?? row.title ?? "").toLowerCase().includes(q) ||
          (row.brand ?? "").toLowerCase().includes(q)
        );
      })
    : rows;
  const qualityFiltered = qualityStatus
    ? baseFiltered.filter(
        (row) => normalizeKey(row.card_quality_state) === qualityStatus,
      )
    : baseFiltered;

  const numericValue = (
    row: PortalProductRow,
    key: Exclude<SortKey, null>,
  ): number | null => {
    const value =
      key === "revenue"
        ? row.revenue
        : key === "profit"
          ? row.profit ?? row.estimated_profit
          : key === "margin"
            ? row.margin
            : key === "quality_score"
              ? row.card_quality_score
              : row.card_quality_issue_count;
    return numberOrNull(value);
  };
  const filtered = sortKey
    ? [...qualityFiltered].sort((a, b) => {
        const av = numericValue(a, sortKey);
        const bv = numericValue(b, sortKey);
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return sortDir === "asc" ? av - bv : bv - av;
      })
    : qualityFiltered;

  const toggleSort = (key: Exclude<SortKey, null>) => {
    if (sortKey !== key) {
      setSortKey(key);
      setSortDir("desc");
    } else if (sortDir === "desc") {
      setSortDir("asc");
    } else {
      setSortKey(null);
      setSortDir("desc");
    }
  };

  const pageRevenue = filtered.reduce((sum, row) => sum + (row.revenue ?? 0), 0);
  const pageProfit = filtered.reduce(
    (sum, row) => sum + (row.profit ?? row.estimated_profit ?? 0),
    0,
  );
  const issueCount = filtered.reduce(
    (sum, row) => sum + (row.card_quality_issue_count ?? 0),
    0,
  );
  const actionCount = filtered.reduce(
    (sum, row) => sum + (row.open_actions_count ?? 0),
    0,
  );

  useEffect(() => {
    const target = loadMoreRef.current;
    if (!target || !hasNextPage) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.some((entry) => entry.isIntersecting);
        if (visible && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      { rootMargin: "700px 0px 700px 0px" },
    );

    observer.observe(target);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, filtered.length]);

  useEffect(() => {
    if (!hasNextPage) return;

    const maybeLoadMore = () => {
      const doc = document.documentElement;
      const remaining = doc.scrollHeight - window.scrollY - window.innerHeight;
      if (remaining < 900 && !isFetchingNextPage) {
        fetchNextPage();
      }
    };

    window.addEventListener("scroll", maybeLoadMore, { passive: true });
    maybeLoadMore();
    return () => window.removeEventListener("scroll", maybeLoadMore);
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, filtered.length]);

  return (
    <PageShell>
      <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold leading-6 text-foreground">
            Товары WB
          </h1>
          <p className="text-xs text-muted-foreground">
            {activeId
              ? isLoading
                ? "Загружаем товары"
                : `${total.toLocaleString("ru-RU")} товаров в списке`
              : "Выберите аккаунт для загрузки товаров"}
          </p>
        </div>
        {activeId ? (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] leading-4 text-muted-foreground">
            <span>
              Загружено <span className="font-semibold text-foreground">{loadedCount.toLocaleString("ru-RU")}</span>
            </span>
            <span>
              Выручка <span className="font-semibold text-foreground">{formatMoney(pageRevenue)}</span>
            </span>
            <span>
              Прибыль{" "}
              <span className={cn("font-semibold text-foreground", pageProfit < 0 && "text-destructive")}>
                {formatMoney(pageProfit)}
              </span>
            </span>
            <span>
              Проблемы/действия{" "}
              <span className="font-semibold text-foreground">
                {issueCount.toLocaleString("ru-RU")} / {actionCount.toLocaleString("ru-RU")}
              </span>
            </span>
          </div>
        ) : null}
      </div>

      {!activeId && <NoAccountSelected />}

      {activeId && (
        <div className="mb-2 rounded-md border bg-card p-1.5 shadow-sm">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-1 flex-col gap-2 sm:flex-row">
              <div className="relative min-w-0 flex-1">
                <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                  }}
                  placeholder="Поиск: nmID, артикул, бренд или название"
                  className="h-8 pl-8 text-xs"
                  disabled={!activeId}
                />
              </div>
              <Select
                value={qualityStatus || "all"}
                onValueChange={(value) => {
                  setQualityStatus(value === "all" ? "" : value);
                }}
                disabled={!activeId}
              >
                <SelectTrigger className="h-8 w-full text-xs sm:w-48">
                  <SelectValue placeholder="Статус карточки" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Все карточки</SelectItem>
                  <SelectItem value="critical">Критично</SelectItem>
                  <SelectItem value="warning">Есть замечания</SelectItem>
                  <SelectItem value="ok">В порядке</SelectItem>
                  <SelectItem value="not_analyzed">Не проверено</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <SortButton
                label="Выручка"
                sortId="revenue"
                sortKey={sortKey}
                sortDir={sortDir}
                onClick={() => toggleSort("revenue")}
              />
              <SortButton
                label="Прибыль"
                sortId="profit"
                sortKey={sortKey}
                sortDir={sortDir}
                onClick={() => toggleSort("profit")}
              />
              <SortButton
                label="Маржа"
                sortId="margin"
                sortKey={sortKey}
                sortDir={sortDir}
                onClick={() => toggleSort("margin")}
              />
              <SortButton
                label="Качество"
                sortId="quality_score"
                sortKey={sortKey}
                sortDir={sortDir}
                onClick={() => toggleSort("quality_score")}
              />
              <SortButton
                label="Проблемы"
                sortId="quality_issues"
                sortKey={sortKey}
                sortDir={sortDir}
                onClick={() => toggleSort("quality_issues")}
              />
            </div>
          </div>
        </div>
      )}

      {activeId && error && (
        <Alert variant="destructive" className="mb-4">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Не удалось загрузить товары</AlertTitle>
          <AlertDescription className="space-y-2">
            <div>{(error as Error).message}</div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              {isFetching ? "Повтор..." : "Повторить"}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {activeId && isLoading && !error && (
        <div className="space-y-1">
          {Array.from({ length: 8 }).map((_, i) => (
            <ProductCardSkeleton key={i} />
          ))}
        </div>
      )}

      {activeId && !isLoading && !error && filtered.length === 0 && (
        <Card className="rounded-md shadow-sm">
          <CardContent className="flex flex-col items-center gap-3 p-10 text-center">
            <PackageOpen className="h-8 w-8 text-muted-foreground" />
            <div className="text-sm font-medium">Товары не найдены</div>
            <div className="max-w-md text-xs text-muted-foreground">
              {debounced
                ? "По запросу ничего не найдено. Попробуйте изменить поиск или статус карточки."
                : "Для выбранного аккаунта и периода нет товаров. Проверьте период вверху страницы."}
            </div>
          </CardContent>
        </Card>
      )}

      {activeId && !isLoading && !error && filtered.length > 0 && (
        <div className="space-y-1">
          {filtered.map((row) => (
            <ProductCard key={row.nm_id} row={row} />
          ))}
        </div>
      )}

      {activeId && !isLoading && !error && filtered.length > 0 && (
        <div ref={loadMoreRef} className="flex justify-center py-3 text-xs text-muted-foreground">
          {isFetchingNextPage
            ? "Загружаем еще товары..."
            : hasNextPage
              ? "Прокрутите ниже, чтобы загрузить еще"
              : `Загружено ${loadedCount.toLocaleString("ru-RU")} из ${total.toLocaleString("ru-RU")}`}
        </div>
      )}
    </PageShell>
  );
}
