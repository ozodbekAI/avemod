// @ts-nocheck
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";
import {
  createABTestCompany,
  extractProductPhotos,
  fetchABTestBalance,
  fetchABTests,
  fetchProductsForABTest,
  startABTestCompany,
  stopABTestCompany,
  updateABTestCompany,
  uploadABTestPhoto,
  type ABTestCompany,
  type ABTestStatus,
  type ProductOption,
} from "@/lib/ab-tests";
import { useAccounts } from "@/lib/account-context";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { PageHeader, PageShell } from "@/components/PageShell";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { EndpointError } from "@/components/EndpointError";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { formatNumber } from "@/lib/format";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Banknote,
  Camera,
  ChevronRight,
  CheckCircle2,
  CircleDot,
  Eye,
  FlaskConical,
  Image as ImageIcon,
  Lock,
  Loader2,
  Package,
  PauseCircle,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trophy,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/ab-tests")({
  component: ABTestsPage,
  validateSearch: (search: Record<string, unknown>) => ({
    nm_id: typeof search.nm_id === "string" ? search.nm_id : undefined,
  }),
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

const STATUSES: ABTestStatus[] = ["running", "pending", "finished", "failed"];
const MIN_VARIANTS = 2;
const MAX_VARIANTS = 5;
const VIEWS_MIN = 1000;
const VIEWS_MAX = 2500;
const VIEWS_STEP = 10;
const CPM_MAX = 1500;
const CPM_STEP = 10;

type SlotItem = {
  id: string;
  url: string;
  fileUrl: string;
  fileName: string | null;
};

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function currency(value: number) {
  return formatNumber(Math.round(value || 0));
}

function confirmWBWrite(preview: Record<string, unknown>, fallback: string) {
  const diff = (preview.diff || {}) as Record<string, unknown>;
  const proposed = Array.isArray(diff.proposed_media)
    ? diff.proposed_media.length
    : Number(preview.photos_count || 0);
  const current = Array.isArray(diff.current_media) ? diff.current_media.length : 0;
  const lines = [
    fallback,
    "",
    `Текущих фото: ${current}`,
    `Новых вариантов: ${proposed}`,
    "После подтверждения запрос может изменить WB кампанию или медиа карточки.",
  ];
  return window.confirm(lines.join("\n"));
}

function makeSlotKey(
  item:
    | SlotItem
    | { fileUrl?: string; url?: string; fileName?: string | null }
    | null,
) {
  return item?.fileUrl || item?.url || item?.fileName || "";
}

function looksLikeUrl(value: string) {
  const raw = String(value || "").trim();
  return (
    raw.startsWith("http://") ||
    raw.startsWith("https://") ||
    raw.startsWith("/")
  );
}

function extractFirstUrl(value: string) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const line = raw.split(/\r?\n/).find((item) => looksLikeUrl(item));
  return line?.trim() || "";
}

function extractUrlFromHtml(value: string) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const attr = raw.match(/(?:src|href)\s*=\s*["']([^"']+)["']/i);
  if (attr?.[1] && looksLikeUrl(attr[1])) return attr[1];
  const css = raw.match(/url\(\s*["']?([^"')\s]+)["']?\s*\)/i);
  if (css?.[1] && looksLikeUrl(css[1])) return css[1];
  const bare = raw.match(/https?:\/\/[^"'<>\s]+/i);
  return bare?.[0] || "";
}

function tryParseDragItem(event: DragEvent<HTMLElement>) {
  const raw =
    event.dataTransfer.getData("photoItem") ||
    event.dataTransfer.getData("application/json") ||
    event.dataTransfer.getData("text/json") ||
    "";
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as
      | { item?: { url?: string; fileUrl?: string; fileName?: string } }
      | { url?: string; fileUrl?: string; fileName?: string };
    return "item" in parsed ? parsed.item || null : parsed;
  } catch {
    return null;
  }
}

function ABTestsPage() {
  const { activeId } = useAccounts();
  const searchParams = Route.useSearch();
  const queryClient = useQueryClient();
  const [view, setView] = useState<"home" | "article" | "panel">("home");
  const [activeTab, setActiveTab] = useState<
    "all" | "running" | "completed" | "issues"
  >("all");
  const [cardQuery, setCardQuery] = useState("");
  const debouncedCardQuery = useDebouncedValue(cardQuery.trim(), 300);
  const [selectedProduct, setSelectedProduct] = useState<ProductOption | null>(
    null,
  );
  const openedFromNmIdRef = useRef<string | null>(null);

  const queries = {
    running: useQuery({
      queryKey: ["ab-tests", activeId, "running"],
      queryFn: () => fetchABTests(activeId!, "running"),
      enabled: !!activeId,
      staleTime: 30_000,
    }),
    pending: useQuery({
      queryKey: ["ab-tests", activeId, "pending"],
      queryFn: () => fetchABTests(activeId!, "pending"),
      enabled: !!activeId,
      staleTime: 30_000,
    }),
    finished: useQuery({
      queryKey: ["ab-tests", activeId, "finished"],
      queryFn: () => fetchABTests(activeId!, "finished"),
      enabled: !!activeId,
      staleTime: 30_000,
    }),
    failed: useQuery({
      queryKey: ["ab-tests", activeId, "failed"],
      queryFn: () => fetchABTests(activeId!, "failed"),
      enabled: !!activeId,
      staleTime: 30_000,
    }),
  } satisfies Record<ABTestStatus, ReturnType<typeof useQuery>>;

  const items = useMemo(() => {
    const all = [
      ...(queries.running.data?.items ?? []),
      ...(queries.pending.data?.items ?? []),
      ...(queries.finished.data?.items ?? []),
      ...(queries.failed.data?.items ?? []),
    ];
    const seen = new Set<number>();
    return all.filter((item) => {
      const id = Number(item.id_company);
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });
  }, [
    queries.running.data,
    queries.pending.data,
    queries.finished.data,
    queries.failed.data,
  ]);

  const refresh = () => {
    for (const status of STATUSES)
      void queryClient.invalidateQueries({
        queryKey: ["ab-tests", activeId, status],
      });
  };
  const productsQ = useQuery({
    queryKey: ["ab-test-products", activeId, debouncedCardQuery],
    queryFn: () => fetchProductsForABTest(activeId!, debouncedCardQuery),
    enabled: !!activeId && view === "article",
    staleTime: 30_000,
  });

  useEffect(() => {
    const requestedNmId = String(searchParams.nm_id || "").trim();
    if (!activeId || !requestedNmId || openedFromNmIdRef.current === requestedNmId) return;
    openedFromNmIdRef.current = requestedNmId;
    setCardQuery(requestedNmId);
    setView("article");
  }, [activeId, searchParams.nm_id]);

  useEffect(() => {
    const requestedNmId = String(searchParams.nm_id || "").trim();
    if (!requestedNmId || view !== "article" || !productsQ.data?.length) return;
    const matched = productsQ.data.find((product) => String(product.nm_id) === requestedNmId);
    if (matched) {
      setSelectedProduct(matched);
      setView("panel");
    }
  }, [productsQ.data, searchParams.nm_id, view]);
  const isLoading = Object.values(queries).some((query) => query.isLoading);
  const isFetching = Object.values(queries).some((query) => query.isFetching);
  const stats = useMemo(
    () => ({
      running: items.filter(
        (item) => normalizeStatus(item.status) === "running",
      ).length,
      finished: items.filter(
        (item) => normalizeStatus(item.status) === "finished",
      ).length,
      issues: items.filter(isAttentionItem).length,
      total: items.length,
    }),
    [items],
  );
  const filtered = useMemo(() => {
    if (activeTab === "running")
      return items.filter((item) => normalizeStatus(item.status) === "running");
    if (activeTab === "completed")
      return items.filter(
        (item) => normalizeStatus(item.status) === "finished",
      );
    if (activeTab === "issues") return items.filter(isAttentionItem);
    return items;
  }, [activeTab, items]);

  const openWizard = () => {
    setSelectedProduct(null);
    setCardQuery("");
    setView("article");
  };
  const closeWizard = async () => {
    setView("home");
    setSelectedProduct(null);
    setCardQuery("");
    await Promise.all(
      STATUSES.map((status) =>
        queryClient.invalidateQueries({
          queryKey: ["ab-tests", activeId, status],
        }),
      ),
    );
  };

  if (!activeId) {
    return (
      <PageShell>
        <PageHeader
          title="A/B тесты"
          description="Проверка главных фото через WB рекламу."
        />
        <NoAccountSelected message="Чтобы запускать A/B тесты, выберите WB-аккаунт в верхней панели." />
      </PageShell>
    );
  }

  if (view === "article") {
    return (
      <PageShell>
        <div className="mb-4 flex items-center justify-between gap-3">
          <Button variant="ghost" onClick={() => setView("home")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Отмена
          </Button>
          <Button disabled={!selectedProduct} onClick={() => setView("panel")}>
            Продолжить
            <ChevronRight className="ml-2 h-4 w-4" />
          </Button>
        </div>

        <PageHeader
          title="Выбор артикула"
          description="Выберите товар для A/B тестирования главного фото."
        />

        <Card>
          <CardContent className="space-y-4 pt-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={cardQuery}
                onChange={(event) => setCardQuery(event.target.value)}
                placeholder="Поиск по названию, артикулу или nmId..."
                className="pl-9"
              />
            </div>
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void productsQ.refetch()}
                disabled={productsQ.isFetching}
              >
                <RefreshCw
                  className={cn(
                    "mr-2 h-4 w-4",
                    productsQ.isFetching && "animate-spin",
                  )}
                />
                {productsQ.isFetching ? "Загрузка..." : "Обновить"}
              </Button>
              <span>Показано: {productsQ.data?.length ?? 0}</span>
            </div>

            <div className="rounded-md border">
              {productsQ.isLoading ? (
                <div className="space-y-2 p-3">
                  {[1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} className="h-20" />
                  ))}
                </div>
              ) : productsQ.data?.length ? (
                <div className="divide-y">
                  {productsQ.data.map((product) => {
                    const photos = extractProductPhotos(product);
                    const preview = photos[0];
                    const selected = selectedProduct?.id === product.id;
                    return (
                      <button
                        key={product.id}
                        type="button"
                        onClick={() => setSelectedProduct(product)}
                        className={cn(
                          "flex w-full items-center gap-3 p-3 text-left hover:bg-muted/60",
                          selected && "bg-muted",
                        )}
                      >
                        <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
                          {preview ? (
                            <img
                              src={preview}
                              alt=""
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <Package className="h-5 w-5 text-muted-foreground" />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium">
                            {product.title || `Карточка ${product.nm_id}`}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            WB: {product.nm_id}
                            {product.vendor_code
                              ? ` · ${product.vendor_code}`
                              : ""}
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            Фото: {photos.length}
                          </div>
                        </div>
                        <div
                          className={cn(
                            "flex h-5 w-5 items-center justify-center rounded-full border",
                            selected && "border-primary bg-primary",
                          )}
                        >
                          {selected ? (
                            <CheckCircle2 className="h-3 w-3 text-primary-foreground" />
                          ) : null}
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="p-8 text-center text-sm text-muted-foreground">
                  Карточки не найдены
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </PageShell>
    );
  }

  if (view === "panel" && selectedProduct) {
    const selectedPhotos = extractProductPhotos(selectedProduct);
    return (
      <PageShell>
        <div className="mb-4 flex items-center justify-between gap-3">
          <Button variant="ghost" onClick={() => void closeWizard()}>
            <ArrowLeft className="mr-2 h-4 w-4" />К списку тестов
          </Button>
          <Button variant="outline" onClick={() => setView("article")}>
            Сменить товар
          </Button>
        </div>

        <Card>
          <CardContent className="flex items-center gap-3 pt-4">
            <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
              {selectedPhotos[0] ? (
                <img
                  src={selectedPhotos[0]}
                  alt=""
                  className="h-full w-full object-cover"
                />
              ) : (
                <Package className="h-5 w-5 text-muted-foreground" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm text-muted-foreground">
                Выбранная карточка
              </div>
              <div className="truncate text-lg font-semibold">
                {selectedProduct.title || `Карточка ${selectedProduct.nm_id}`}
              </div>
              <div className="truncate text-sm text-muted-foreground">
                WB: {selectedProduct.nm_id}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="mt-4">
          <ABTestWizard
            accountId={activeId}
            open
            embedded
            initialProduct={selectedProduct}
            onOpenChange={(nextOpen) => {
              if (!nextOpen) void closeWizard();
            }}
          />
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="Фото-тесты главного фото"
        description="Узнайте, какое фото привлекает больше покупателей. Система последовательно покажет каждый вариант и определит лучший по CTR."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={refresh} disabled={isFetching}>
              <RefreshCw
                className={cn("mr-2 h-4 w-4", isFetching && "animate-spin")}
              />
              Обновить
            </Button>
            <Button onClick={openWizard}>
              <Plus className="mr-2 h-4 w-4" />
              Запустить новый тест
            </Button>
          </div>
        }
      />

      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <MetricCardCompact label="Активных" value={String(stats.running)} />
        <MetricCardCompact label="Завершено" value={String(stats.finished)} />
        <MetricCardCompact
          label="Требуют внимания"
          value={String(stats.issues)}
        />
      </div>

      <Alert className="mb-4">
        <AlertTitle>Последовательный фото-тест</AlertTitle>
        <AlertDescription>
          Варианты оцениваются поочерёдно, а не одновременно. Результаты
          индикативные: время суток и сезон могут влиять на CTR.
        </AlertDescription>
      </Alert>

      <div className="mb-4 flex flex-wrap gap-2">
        <FilterButton
          active={activeTab === "all"}
          onClick={() => setActiveTab("all")}
        >
          Все ({stats.total})
        </FilterButton>
        <FilterButton
          active={activeTab === "running"}
          onClick={() => setActiveTab("running")}
        >
          <CircleDot className="mr-1 h-3 w-3" />
          Активные ({stats.running})
        </FilterButton>
        <FilterButton
          active={activeTab === "completed"}
          onClick={() => setActiveTab("completed")}
        >
          <CheckCircle2 className="mr-1 h-3 w-3" />
          Завершённые ({stats.finished})
        </FilterButton>
        <FilterButton
          active={activeTab === "issues"}
          onClick={() => setActiveTab("issues")}
        >
          <AlertTriangle className="mr-1 h-3 w-3" />
          Ошибки и стоп ({stats.issues})
        </FilterButton>
      </div>

      {isLoading ? (
        <div className="grid gap-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      ) : filtered.length ? (
        <div className="grid gap-3">
          {filtered.map((item) => (
            <ABTestCard
              key={item.id_company}
              accountId={activeId}
              item={item}
            />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex min-h-72 flex-col items-center justify-center gap-3 text-center">
            <FlaskConical className="h-10 w-10 text-muted-foreground" />
            <div>
              <div className="font-medium">A/B тестов пока нет</div>
              <p className="mt-1 text-sm text-muted-foreground">
                Выберите карточку и добавьте минимум два фото-варианта.
              </p>
            </div>
            <Button onClick={openWizard}>
              <Plus className="mr-2 h-4 w-4" />
              Создать тест
            </Button>
          </CardContent>
        </Card>
      )}
    </PageShell>
  );
}

function ABTestCard({
  accountId,
  item,
}: {
  accountId: number;
  item: ABTestCompany;
}) {
  const queryClient = useQueryClient();
  const status = normalizeStatus(item.status);
  const startMut = useMutation({
    mutationFn: async () => {
      const preview = await startABTestCompany(accountId, item.id_company);
      if (preview.requires_confirmation) {
        if (!confirmWBWrite(preview, "Запустить A/B тест и применить фото к WB карточке?")) {
          throw new Error("Запуск A/B теста отменён");
        }
      }
      return startABTestCompany(accountId, item.id_company, { confirm: true });
    },
    onSuccess: async () => {
      toast.success("Тест запущен");
      await queryClient.invalidateQueries({
        queryKey: ["ab-tests", accountId],
      });
    },
    onError: (error: unknown) =>
      toast.error(errorMessage(error, "Не удалось запустить тест")),
  });
  const stopMut = useMutation({
    mutationFn: async () => {
      const preview = await stopABTestCompany(accountId, item.id_company);
      if (preview.requires_confirmation) {
        if (!confirmWBWrite(preview, "Остановить A/B тест и восстановить медиа карточки?")) {
          throw new Error("Остановка A/B теста отменена");
        }
      }
      return stopABTestCompany(accountId, item.id_company, { confirm: true });
    },
    onSuccess: async () => {
      toast.success("Тест остановлен");
      await queryClient.invalidateQueries({
        queryKey: ["ab-tests", accountId],
      });
    },
    onError: (error: unknown) =>
      toast.error(errorMessage(error, "Не удалось остановить тест")),
  });

  const totalShows =
    item.photos?.reduce((sum, photo) => sum + (photo.shows || 0), 0) ?? 0;
  const totalClicks =
    item.photos?.reduce((sum, photo) => sum + (photo.clicks || 0), 0) ?? 0;
  const ctr = totalShows > 0 ? (totalClicks / totalShows) * 100 : 0;
  const preview =
    item.photos?.find((photo) => photo.is_winner)?.preview_url ||
    item.photos?.[0]?.preview_url ||
    item.photos?.[0]?.file_url;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="truncate text-base">
              {item.title || `nmID ${item.nm_id}`}
            </CardTitle>
            <div className="mt-1 text-xs text-muted-foreground">
              nmID {item.nm_id}
              {item.wb_advert_id ? ` · advert ${item.wb_advert_id}` : ""}
            </div>
          </div>
          <StatusBadge status={status} decision={item.winner_decision} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-3">
          <div className="flex h-24 w-20 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
            {preview ? (
              <img
                src={preview}
                alt=""
                className="h-full w-full object-cover"
              />
            ) : (
              <FlaskConical className="h-6 w-6 text-muted-foreground" />
            )}
          </div>
          <div className="grid flex-1 grid-cols-2 gap-2 text-sm">
            <Metric label="Показы" value={formatNumber(totalShows)} />
            <Metric label="Клики" value={formatNumber(totalClicks)} />
            <Metric label="CTR" value={`${ctr.toFixed(2)}%`} />
            <Metric
              label="Бюджет"
              value={`${formatNumber(item.spend_rub || item.estimated_spend_rub || 0)} ₽`}
            />
          </div>
        </div>
        {item.last_error ? (
          <Alert
            variant={status === "failed" ? "destructive" : "default"}
            className="py-2"
          >
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription className="line-clamp-2 text-xs">
              {item.last_error}
            </AlertDescription>
          </Alert>
        ) : null}
        <div className="flex items-center justify-between gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link
              to="/ab-tests/$companyId"
              params={{ companyId: String(item.id_company) }}
            >
              <Eye className="mr-2 h-4 w-4" />
              Детали
            </Link>
          </Button>
          <div className="flex gap-2">
            {item.can_start ? (
              <Button
                size="sm"
                onClick={() => startMut.mutate()}
                disabled={startMut.isPending}
              >
                {startMut.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-2 h-4 w-4" />
                )}
                Старт
              </Button>
            ) : null}
            {item.can_stop ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => stopMut.mutate()}
                disabled={stopMut.isPending}
              >
                {stopMut.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <PauseCircle className="mr-2 h-4 w-4" />
                )}
                Стоп
              </Button>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ABTestWizard({
  accountId,
  open,
  onOpenChange,
  embedded = false,
  initialProduct = null,
}: {
  accountId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  embedded?: boolean;
  initialProduct?: ProductOption | null;
}) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<1 | 2>(1);
  const [companyId, setCompanyId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search.trim(), 300);
  const [selected, setSelected] = useState<ProductOption | null>(null);
  const [skipCurrentMain, setSkipCurrentMain] = useState(false);
  const [slots, setSlots] = useState<(SlotItem | null)[]>(() =>
    Array.from({ length: MAX_VARIANTS }).map(() => null),
  );
  const [slotUploading, setSlotUploading] = useState<boolean[]>(() =>
    Array.from({ length: MAX_VARIANTS }).map(() => false),
  );
  const [everUsedKeys, setEverUsedKeys] = useState<Set<string>>(
    () => new Set(),
  );
  const [viewsPerPhoto, setViewsPerPhoto] = useState(1800);
  const [cpm, setCpm] = useState(600);
  const [minCpm, setMinCpm] = useState(0);
  const [keepWinner, setKeepWinner] = useState(true);
  const [deleteTestPhotos, setDeleteTestPhotos] = useState(true);
  const [usePromoBonus, setUsePromoBonus] = useState(false);
  const originalTitleRef = useRef("");

  const productsQ = useQuery({
    queryKey: ["ab-test-products", accountId, debouncedSearch],
    queryFn: () => fetchProductsForABTest(accountId, debouncedSearch),
    enabled: open && !embedded,
    staleTime: 30_000,
  });
  const balanceQ = useQuery({
    queryKey: ["ab-test-balance", accountId],
    queryFn: () => fetchABTestBalance(accountId),
    enabled: open,
    staleTime: 30_000,
  });

  useEffect(() => {
    originalTitleRef.current = selected?.title || "";
  }, [selected?.id, selected?.title]);

  useEffect(() => {
    if (embedded && initialProduct) {
      setSelected(initialProduct);
      originalTitleRef.current = initialProduct.title || "";
    }
  }, [embedded, initialProduct?.id, initialProduct]);

  const productPhotos = useMemo(
    () => (selected ? extractProductPhotos(selected) : []),
    [selected],
  );
  const productPhotoItems = useMemo(
    () =>
      productPhotos.map((url, index) => ({
        id: `card_photo_${index}_${url}`,
        url,
        fileUrl: url,
        fileName: index === 0 ? "Главное фото" : `Фото карточки ${index + 1}`,
      })),
    [productPhotos],
  );
  const derivedMain = productPhotos[0]
    ? { url: productPhotos[0], fileName: "Главное фото" }
    : null;
  const includeMainPhoto = !skipCurrentMain;
  const isLockedSlot = (idx: number) => includeMainPhoto && idx === 0;

  const filledVariantCount = useMemo(
    () =>
      slots.filter(
        (slot, idx) => Boolean(slot) && !(includeMainPhoto && idx === 0),
      ).length,
    [slots, includeMainPhoto],
  );
  const totalPhotosCount = useMemo(() => {
    const main = includeMainPhoto && derivedMain?.url ? 1 : 0;
    return main + filledVariantCount;
  }, [derivedMain?.url, filledVariantCount, includeMainPhoto]);
  const promoAvailableRub = Number(
    balanceQ.data?.promo_bonus_rub ||
      ((
        balanceQ.data?.raw as
          | { bonus?: number; cashbacks?: Array<{ sum?: number }> }
          | undefined
      )?.cashbacks?.[0]?.sum ??
        0),
  );

  const estimatedSpend = useMemo(() => {
    const totalImpressions =
      Math.max(totalPhotosCount, MIN_VARIANTS) * viewsPerPhoto;
    return Math.max(
      1000,
      Math.ceil(((totalImpressions / 1000) * cpm * 1.1) / 100) * 100,
    );
  }, [totalPhotosCount, viewsPerPhoto, cpm]);

  useEffect(() => {
    if (minCpm && cpm < minCpm) setCpm(minCpm);
  }, [cpm, minCpm]);

  const disabledReason = useMemo(() => {
    if (!selected) return "Выберите карточку для A/B теста.";
    if (!derivedMain?.url)
      return "A/B тест недоступен: у карточки нет главного фото.";
    return "";
  }, [derivedMain?.url, selected]);

  const buildPhotosPayload = () => {
    const photos: {
      order: number;
      file_url: string;
      file_name?: string | null;
    }[] = [];
    if (includeMainPhoto && derivedMain?.url) {
      photos.push({
        order: 1,
        file_url: derivedMain.url,
        file_name: derivedMain.fileName,
      });
      for (let i = 1; i < MAX_VARIANTS; i += 1) {
        const slot = slots[i];
        if (slot)
          photos.push({
            order: i + 1,
            file_url: slot.fileUrl,
            file_name: slot.fileName,
          });
      }
      return photos.slice(0, MAX_VARIANTS);
    }
    for (let i = 0; i < MAX_VARIANTS; i += 1) {
      const slot = slots[i];
      if (slot)
        photos.push({
          order: i + 1,
          file_url: slot.fileUrl,
          file_name: slot.fileName,
        });
    }
    return photos.slice(0, MAX_VARIANTS);
  };

  const canContinue =
    selected && !disabledReason && totalPhotosCount >= MIN_VARIANTS;
  const canStart =
    selected &&
    companyId &&
    !disabledReason &&
    totalPhotosCount >= MIN_VARIANTS &&
    viewsPerPhoto >= 1000 &&
    cpm > 0;

  const clampCpm = (value: number) =>
    Math.max(Number.isFinite(value) ? value : 0, minCpm || 0);
  const markEverUsed = (key: string) => {
    if (!key) return;
    setEverUsedKeys((prev) => new Set(prev).add(key));
  };
  const canUseKey = (key: string) => {
    if (!key) return true;
    if (everUsedKeys.has(key)) return false;
    if (includeMainPhoto && derivedMain?.url && key === derivedMain.url) {
      return false;
    }
    return !new Set(slots.filter(Boolean).map((slot) => makeSlotKey(slot))).has(
      key,
    );
  };
  const setUploadingAt = (idx: number, value: boolean) => {
    setSlotUploading((prev) => {
      const next = [...prev];
      next[idx] = value;
      return next;
    });
  };
  const putIntoSlot = (
    idx: number,
    item: { url: string; fileName?: string | null },
  ) => {
    if (isLockedSlot(idx)) {
      toast.error(
        "Первый слот занят текущим главным фото и недоступен для замены",
      );
      return;
    }
    const url = String(item.url || "").trim();
    if (!url) return;
    const key = url;
    if (!canUseKey(key)) {
      toast.error(
        "Этот файл уже использовался. Нельзя поставить одно и то же фото дважды.",
      );
      return;
    }
    setSlots((prev) => {
      const next = [...prev];
      next[idx] = {
        id: `${Date.now()}_${Math.random().toString(36).slice(2)}`,
        url,
        fileUrl: url,
        fileName: item.fileName || null,
      };
      return next;
    });
    markEverUsed(key);
  };
  const firstWritableSlot = () =>
    slots.findIndex((slot, index) => !slot && !isLockedSlot(index));
  const addCardPhotoToFirstSlot = (item: SlotItem) => {
    const index = firstWritableSlot();
    if (index < 0) {
      toast.error("Нет свободного слота для фото");
      return;
    }
    putIntoSlot(index, item);
  };
  const clearSlot = (idx: number) => {
    if (isLockedSlot(idx)) return;
    setSlots((prev) => {
      const next = [...prev];
      next[idx] = null;
      return next;
    });
  };
  const uploadFileToSlot = async (idx: number, file?: File | null) => {
    if (!file) return;
    if (isLockedSlot(idx)) {
      toast.error(
        "Первый слот занят текущим главным фото и недоступен для загрузки",
      );
      return;
    }
    setUploadingAt(idx, true);
    try {
      const res = await uploadABTestPhoto(file, accountId);
      const url = res.file_url || res.url || res.image_url;
      if (!url) throw new Error("Upload response has no url");
      putIntoSlot(idx, { url, fileName: res.file_name || file.name || null });
      toast.success("Фото загружено");
    } catch (error: unknown) {
      toast.error(errorMessage(error, "Не удалось загрузить фото"));
    } finally {
      setUploadingAt(idx, false);
    }
  };
  const handleDropToSlot = async (
    idx: number,
    event: DragEvent<HTMLDivElement>,
  ) => {
    event.preventDefault();
    if (isLockedSlot(idx)) {
      toast.error(
        "Первый слот занят текущим главным фото и недоступен для замены",
      );
      return;
    }
    const dragItem = tryParseDragItem(event);
    if (dragItem) {
      const url = String(dragItem.fileUrl || dragItem.url || "").trim();
      if (url) {
        putIntoSlot(idx, {
          url,
          fileName: dragItem.fileName || null,
        });
        return;
      }
    }
    const url =
      extractFirstUrl(event.dataTransfer.getData("text/uri-list")) ||
      extractFirstUrl(event.dataTransfer.getData("text/plain")) ||
      extractUrlFromHtml(event.dataTransfer.getData("text/html"));
    if (url) {
      putIntoSlot(idx, { url });
      return;
    }
    const file = event.dataTransfer.files?.[0];
    if (file) await uploadFileToSlot(idx, file);
  };
  const shiftSlotsForMode = (nextSkipCurrentMain: boolean) => {
    setSlots((prev) => {
      const next = [...prev];
      if (nextSkipCurrentMain)
        return [
          next[1] || null,
          next[2] || null,
          next[3] || null,
          next[4] || null,
          null,
        ];
      const dropped = next[4];
      if (dropped)
        toast.message(
          "Одно фото убрано: при включении контроля доступно только 4 слота для загрузки",
        );
      return [
        null,
        next[0] || null,
        next[1] || null,
        next[2] || null,
        next[3] || null,
      ];
    });
    setSlotUploading(Array.from({ length: MAX_VARIANTS }).map(() => false));
  };

  const createMut = useMutation({
    mutationFn: async () => {
      if (!selected) throw new Error("Товар не выбран");
      if (disabledReason) throw new Error(disabledReason);
      const photos = buildPhotosPayload();
      const draftPayload = {
        nm_id: selected.nm_id,
        card_id: selected.id,
        product_card_id: selected.id,
        title: selected.title || `A/B ${selected.nm_id}`,
        from_main: includeMainPhoto,
        main_photo_url: includeMainPhoto ? derivedMain?.url || null : null,
        max_slots: 5,
        photos,
        photos_count: photos.length,
        keep_winner_as_main: keepWinner,
        delete_test_photos: deleteTestPhotos,
      };
      const preview = await createABTestCompany(accountId, draftPayload);
      if (preview.requires_confirmation) {
        if (!confirmWBWrite(preview, "Создать WB кампанию для A/B теста?")) {
          throw new Error("Создание WB кампании отменено");
        }
      }
      const createRes = await createABTestCompany(accountId, {
        ...draftPayload,
        preview_confirmed: true,
      });
      const companyId = Number(createRes.id_company || createRes.company_id);
      if (!Number.isFinite(companyId) || companyId <= 0) {
        throw new Error("Backend не вернул id_company");
      }
      return createRes;
    },
    onSuccess: async (res) => {
      const id = Number(res.id_company || res.company_id);
      setCompanyId(id);
      const nextMinCpm = Number(res.min_cpm || 0);
      if (Number.isFinite(nextMinCpm) && nextMinCpm > 0) {
        setMinCpm(nextMinCpm);
        setCpm((prev) => Math.max(prev, nextMinCpm));
      }
      await queryClient.invalidateQueries({
        queryKey: ["ab-test-balance", accountId],
      });
      setStep(2);
      toast.success("Компания создана");
    },
    onError: (error: unknown) =>
      toast.error(errorMessage(error, "Не удалось создать компанию")),
  });

  const startMut = useMutation({
    mutationFn: async () => {
      if (!selected) throw new Error("Товар не выбран");
      if (!companyId) throw new Error("Сначала создайте кампанию");
      const photos = buildPhotosPayload();
      const finalTitle = selected.title || `A/B ${selected.nm_id}`;
      const draftPayload = {
        id_company: companyId,
        company_id: companyId,
        nm_id: selected.nm_id,
        card_id: selected.id,
        product_card_id: selected.id,
        title: finalTitle,
        title_changed:
          finalTitle !== (originalTitleRef.current || selected.title),
        from_main: includeMainPhoto,
        max_slots: 5,
        photos_count: photos.length,
        views_per_photo: viewsPerPhoto,
        cpm,
        spend_rub: estimatedSpend,
        estimated_spend_rub: estimatedSpend,
        auto_deposit: true,
        payment_source: "balance",
        use_promo_bonus: usePromoBonus,
        keep_winner_as_main: keepWinner,
        delete_test_photos: deleteTestPhotos,
        photos,
      };
      const preview = await updateABTestCompany(accountId, draftPayload);
      if (preview.requires_confirmation) {
        if (!confirmWBWrite(preview, "Запустить A/B тест и применить первое фото к WB карточке?")) {
          throw new Error("Запуск A/B теста отменён");
        }
      }
      return updateABTestCompany(accountId, {
        ...draftPayload,
        preview_confirmed: true,
      });
    },
    onSuccess: async () => {
      toast.success("Запрос на запуск отправлен");
      handleDialogOpenChange(false);
      setStep(1);
      setCompanyId(null);
      setSearch("");
      setSelected(null);
      setSlots(Array.from({ length: MAX_VARIANTS }).map(() => null));
      setEverUsedKeys(new Set());
      setViewsPerPhoto(1800);
      setCpm(600);
      setMinCpm(0);
      setKeepWinner(true);
      setDeleteTestPhotos(true);
      setUsePromoBonus(false);
      await queryClient.invalidateQueries({
        queryKey: ["ab-tests", accountId],
      });
    },
    onError: (error: unknown) =>
      toast.error(errorMessage(error, "Не удалось запустить тест")),
  });

  const selectProduct = (product: ProductOption) => {
    setSelected(product);
    setStep(1);
    setCompanyId(null);
    setMinCpm(0);
    setSkipCurrentMain(false);
    setSlots(Array.from({ length: MAX_VARIANTS }).map(() => null));
    setEverUsedKeys(new Set());
  };

  const resetWizard = () => {
    setStep(1);
    setCompanyId(null);
    setSearch("");
    setSelected(null);
    setSkipCurrentMain(false);
    setSlots(Array.from({ length: MAX_VARIANTS }).map(() => null));
    setSlotUploading(Array.from({ length: MAX_VARIANTS }).map(() => false));
    setEverUsedKeys(new Set());
    setViewsPerPhoto(1800);
    setCpm(600);
    setMinCpm(0);
    setKeepWinner(true);
    setDeleteTestPhotos(true);
    setUsePromoBonus(false);
  };

  const handleDialogOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen);
    if (!nextOpen) resetWizard();
  };

  const content = (
    <>
      {embedded ? (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <div className="text-2xl font-semibold">A/B тест главного фото</div>
            <div className="mt-1 text-sm text-muted-foreground">
              Можно тестировать от 2 до 5 фото: текущее главное + новые, либо
              только новые.
            </div>
          </div>
          <div className="text-right text-sm text-muted-foreground">
            <div className="font-medium text-foreground">
              Рассчитанный расход
            </div>
            <div className="mt-0.5">≈ {currency(estimatedSpend)} ₽</div>
            <div className="text-xs">минимум 1000₽, округление до 100₽</div>
          </div>
        </div>
      ) : (
        <DialogHeader>
          <DialogTitle>Новый A/B тест главного фото</DialogTitle>
          <DialogDescription>
            1) выберите фото и проверьте preview, 2) подтвердите WB кампанию,
            показы, CPM и запуск теста.
          </DialogDescription>
        </DialogHeader>
      )}

      <div className="grid grid-cols-2 overflow-hidden rounded-md border">
        <button
          type="button"
          onClick={() => {
            setStep(1);
            setCompanyId(null);
          }}
          className={cn(
            "border-r px-4 py-2 text-sm font-semibold",
            step === 1 ? "bg-muted" : "hover:bg-muted/60",
          )}
        >
          1) Фото
        </button>
        <button
          type="button"
          onClick={() => {
            if (step === 2) return;
            if (!canContinue) {
              toast.error("Выберите товар и минимум два фото.");
              return;
            }
            createMut.mutate();
          }}
          disabled={createMut.isPending}
          className={cn(
            "px-4 py-2 text-sm font-semibold",
            step === 2 ? "bg-muted" : "hover:bg-muted/60",
          )}
        >
          2) Кампания
        </button>
      </div>

      <div
        className={cn(
          "grid gap-4",
          embedded ? "grid-cols-1" : "lg:grid-cols-[minmax(280px,360px)_1fr]",
        )}
      >
        <div
          className={cn(
            "space-y-3",
            (embedded || step === 2) && "hidden lg:hidden",
          )}
        >
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Поиск по nmID, артикулу или названию"
              className="pl-9"
            />
          </div>
          <div className="max-h-[360px] overflow-y-auto rounded-md border">
            {productsQ.isLoading ? (
              <div className="space-y-2 p-3">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-16" />
                ))}
              </div>
            ) : productsQ.data?.length ? (
              <div className="divide-y">
                {productsQ.data.map((product) => {
                  const photos = extractProductPhotos(product);
                  const preview = photos[0];
                  const active = selected?.id === product.id;
                  return (
                    <button
                      key={product.id}
                      type="button"
                      onClick={() => selectProduct(product)}
                      className={cn(
                        "flex w-full items-center gap-3 p-3 text-left hover:bg-muted/60",
                        active && "bg-muted",
                      )}
                    >
                      <div className="flex h-16 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
                        {preview ? (
                          <img
                            src={preview}
                            alt=""
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <FlaskConical className="h-5 w-5 text-muted-foreground" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">
                          {product.title || `nmID ${product.nm_id}`}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          nmID {product.nm_id}
                          {product.vendor_code
                            ? ` · ${product.vendor_code}`
                            : ""}
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          Фото: {photos.length}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="p-6 text-center text-sm text-muted-foreground">
                Карточки не найдены
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-3 pt-4">
              {selected ? (
                <div>
                  <div className="text-sm font-medium">
                    {selected.title || `nmID ${selected.nm_id}`}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    nmID {selected.nm_id}
                    {companyId ? ` · кампания ${companyId}` : ""}
                  </div>
                </div>
              ) : null}
              {selected ? (
                <div className="rounded-md border bg-muted/20 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Фото из карточки
                      </div>
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        Нажмите на фото, чтобы поставить его в первый свободный
                        слот, или перетащите в нужный слот.
                      </div>
                    </div>
                    <Badge variant="outline">
                      {productPhotoItems.length} фото
                    </Badge>
                  </div>
                  {productPhotoItems.length ? (
                    <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-6">
                      {productPhotoItems.map((photo, index) => {
                        const key = makeSlotKey(photo);
                        const usedInSlot = slots.some(
                          (slot) => makeSlotKey(slot) === key,
                        );
                        const lockedMain =
                          includeMainPhoto &&
                          index === 0 &&
                          derivedMain?.url === photo.url;
                        const everUsed = everUsedKeys.has(key);
                        const disabled = lockedMain || usedInSlot || everUsed;
                        return (
                          <button
                            key={photo.id}
                            type="button"
                            draggable={!disabled}
                            disabled={disabled}
                            onClick={() => addCardPhotoToFirstSlot(photo)}
                            onDragStart={(event) => {
                              event.dataTransfer.setData(
                                "photoItem",
                                JSON.stringify({
                                  url: photo.url,
                                  fileUrl: photo.fileUrl,
                                  fileName: photo.fileName,
                                }),
                              );
                              event.dataTransfer.setData(
                                "text/plain",
                                photo.url,
                              );
                            }}
                            className={cn(
                              "group relative aspect-square overflow-hidden rounded-md border bg-background text-left transition",
                              disabled
                                ? "cursor-not-allowed opacity-55"
                                : "hover:border-primary hover:ring-2 hover:ring-primary/20",
                            )}
                            title={
                              lockedMain
                                ? "Это текущее главное фото"
                                : usedInSlot || everUsed
                                  ? "Фото уже использовано"
                                  : "Добавить в слот"
                            }
                          >
                            <img
                              src={photo.url}
                              alt=""
                              className="h-full w-full object-cover"
                            />
                            <div className="absolute inset-x-0 bottom-0 bg-background/90 px-1.5 py-1 text-[10px] font-medium">
                              {lockedMain
                                ? "Главное"
                                : usedInSlot || everUsed
                                  ? "В слоте"
                                  : `Фото ${index + 1}`}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="mt-3 rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">
                      У карточки нет дополнительных фото для выбора.
                    </div>
                  )}
                </div>
              ) : null}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <label className="flex select-none items-center gap-2 text-sm text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={skipCurrentMain}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      shiftSlotsForMode(checked);
                      setSkipCurrentMain(checked);
                      setCompanyId(null);
                    }}
                  />
                  Не тестировать текущую главную (5 новых фото)
                </label>
                <div className="text-sm text-muted-foreground">
                  Загружено:{" "}
                  <span className="font-semibold text-foreground">
                    {totalPhotosCount}
                  </span>{" "}
                  / {MAX_VARIANTS}
                </div>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
                {Array.from({ length: MAX_VARIANTS }).map((_, index) => {
                  const slot = slots[index];
                  const locked = isLockedSlot(index);
                  return (
                    <div
                      key={slot?.id || `slot_${index}`}
                      className="min-w-0 overflow-hidden rounded-md border bg-background"
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => void handleDropToSlot(index, event)}
                    >
                      <div className="relative aspect-square bg-muted">
                        {locked ? (
                          <>
                            {derivedMain?.url ? (
                              <img
                                src={derivedMain.url}
                                alt=""
                                className="h-full w-full object-cover"
                              />
                            ) : (
                              <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                                Нет фото
                              </div>
                            )}
                            <Badge
                              variant="secondary"
                              className="absolute bottom-2 left-2 gap-1"
                            >
                              <Lock className="h-3 w-3" />
                              Главное
                            </Badge>
                          </>
                        ) : slot?.url ? (
                          <>
                            <img
                              src={slot.url}
                              alt=""
                              className="h-full w-full object-cover"
                            />
                            <Button
                              type="button"
                              size="icon"
                              variant="secondary"
                              className="absolute right-2 top-2 h-7 w-7"
                              onClick={() => clearSlot(index)}
                            >
                              <X className="h-4 w-4" />
                            </Button>
                          </>
                        ) : (
                          <div className="flex h-full flex-col items-center justify-center px-3 text-center">
                            {slotUploading[index] ? (
                              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                            ) : (
                              <Upload className="h-5 w-5 text-muted-foreground" />
                            )}
                            <div className="mt-2 text-xs text-muted-foreground">
                              Перетащите или загрузите
                            </div>
                            <label className="mt-3 inline-flex cursor-pointer items-center justify-center gap-2 rounded-md bg-muted px-3 py-2 text-xs font-semibold hover:bg-muted/80">
                              <Upload className="h-4 w-4" />
                              {slotUploading[index]
                                ? "Загрузка..."
                                : "Загрузить"}
                              <input
                                type="file"
                                accept="image/*"
                                className="hidden"
                                disabled={locked || slotUploading[index]}
                                onChange={(event) => {
                                  void uploadFileToSlot(
                                    index,
                                    event.target.files?.[0],
                                  );
                                  event.currentTarget.value = "";
                                }}
                              />
                            </label>
                          </div>
                        )}
                      </div>
                      <div className="truncate px-3 py-2 text-xs text-muted-foreground">
                        {locked
                          ? "Главное (контроль)"
                          : slot?.fileName || `Слот ${index + 1}`}
                      </div>
                    </div>
                  );
                })}
              </div>
              {totalPhotosCount < MIN_VARIANTS ? (
                <Alert>
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    Для запуска нужно минимум два фото-варианта.
                  </AlertDescription>
                </Alert>
              ) : null}
            </CardContent>
          </Card>

          {step === 2 ? (
            <>
              <div className="space-y-3 rounded-md border p-3">
                <label className="flex items-center justify-between gap-3 text-sm">
                  <span>Оставить победителя главным фото</span>
                  <input
                    type="checkbox"
                    checked={keepWinner}
                    onChange={(event) => setKeepWinner(event.target.checked)}
                  />
                </label>
                <label className="flex items-center justify-between gap-3 text-sm">
                  <span>Удалять тестовые фото после завершения</span>
                  <input
                    type="checkbox"
                    checked={deleteTestPhotos}
                    onChange={(event) =>
                      setDeleteTestPhotos(event.target.checked)
                    }
                  />
                </label>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Показов на фото</Label>
                  <Input
                    type="number"
                    min={VIEWS_MIN}
                    value={viewsPerPhoto}
                    onChange={(event) =>
                      setViewsPerPhoto(Number(event.target.value || VIEWS_MIN))
                    }
                  />
                  <input
                    type="range"
                    min={VIEWS_MIN}
                    max={VIEWS_MAX}
                    step={VIEWS_STEP}
                    value={viewsPerPhoto}
                    onChange={(event) =>
                      setViewsPerPhoto(Number(event.target.value))
                    }
                    className="w-full"
                  />
                </div>
                <div className="space-y-1">
                  <Label>CPM, ₽</Label>
                  <Input
                    type="number"
                    min={minCpm || 1}
                    step={CPM_STEP}
                    value={cpm}
                    onChange={(event) =>
                      setCpm(clampCpm(Number(event.target.value || 0)))
                    }
                    onBlur={(event) =>
                      setCpm(clampCpm(Number(event.target.value || 0)))
                    }
                  />
                  {minCpm ? (
                    <div className="text-xs text-muted-foreground">
                      Минимальная ставка: {formatNumber(minCpm)} ₽
                    </div>
                  ) : null}
                  <input
                    type="range"
                    min={minCpm || 0}
                    max={CPM_MAX}
                    step={CPM_STEP}
                    value={cpm}
                    onChange={(event) =>
                      setCpm(clampCpm(Number(event.target.value)))
                    }
                    className="w-full"
                  />
                </div>
              </div>

              <div className="rounded-md border p-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Количество фото</span>
                  <strong>{totalPhotosCount}</strong>
                </div>
                <div className="mt-1 flex justify-between">
                  <span className="text-muted-foreground">Оценка бюджета</span>
                  <strong>{formatNumber(estimatedSpend)} ₽</strong>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  ({totalPhotosCount} × {viewsPerPhoto} × {cpm}/1000) +10%,
                  минимум 1000 ₽, округление до 100 ₽
                </div>
                <div className="mt-1 flex justify-between">
                  <span className="text-muted-foreground">Баланс WB</span>
                  <span>{formatNumber(balanceQ.data?.balance ?? 0)} ₽</span>
                </div>
                <div className="mt-1 flex justify-between">
                  <span className="text-muted-foreground">Промо-бонусы</span>
                  <span>{currency(promoAvailableRub)} ₽</span>
                </div>
              </div>

              <label className="flex items-center justify-between gap-2 text-sm">
                <span>Использовать промо-бонусы</span>
                <input
                  type="checkbox"
                  checked={usePromoBonus}
                  disabled={promoAvailableRub <= 0}
                  onChange={(event) => setUsePromoBonus(event.target.checked)}
                />
              </label>

              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Запуск теста предполагает</AlertTitle>
                <AlertDescription>
                  Создание рекламной кампании уже выполнено. При запуске будет
                  пополнен бюджет, выставлен CPM, первое фото станет главным,
                  дальше ротация пойдет автоматически.
                </AlertDescription>
              </Alert>
            </>
          ) : (
            <div className="rounded-md border p-3 text-sm text-muted-foreground">
              Сначала создайте WB кампанию. Настройки показов, CPM и бюджета
              появятся на втором шаге.
            </div>
          )}
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={() => handleDialogOpenChange(false)}>
          Отмена
        </Button>
        {step === 1 ? (
          <Button
            onClick={() => createMut.mutate()}
            disabled={!canContinue || createMut.isPending}
          >
            {createMut.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <ArrowRight className="mr-2 h-4 w-4" />
            )}
            Продолжить
          </Button>
        ) : (
          <Button
            onClick={() => startMut.mutate()}
            disabled={!canStart || startMut.isPending}
          >
            {startMut.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            Запустить тест
          </Button>
        )}
        {step === 2 ? (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setStep(1);
              setCompanyId(null);
            }}
            disabled={startMut.isPending}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Назад
          </Button>
        ) : null}
      </DialogFooter>
    </>
  );

  if (embedded) {
    return (
      <Card>
        <CardContent className="space-y-4 pt-4">{content}</CardContent>
      </Card>
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleDialogOpenChange}>
      <DialogContent className="max-w-5xl">{content}</DialogContent>
    </Dialog>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/30 px-2 py-1.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}

function MetricCardCompact({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="text-sm text-muted-foreground">{label}</div>
        <div className="mt-1 text-2xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}

function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Button
      type="button"
      variant={active ? "default" : "outline"}
      size="sm"
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

function isAttentionItem(item: ABTestCompany) {
  const status = normalizeStatus(item.status);
  if (status === "failed" || status === "stopped") return true;
  return status === "pending" && Boolean((item.last_error || "").trim());
}

function StatusBadge({
  status,
  decision,
}: {
  status: string;
  decision?: string | null;
}) {
  if (decision === "winner_found")
    return (
      <Badge className="bg-success text-white">
        <Trophy className="mr-1 h-3 w-3" />
        Победитель
      </Badge>
    );
  if (decision === "insufficient_data")
    return <Badge variant="outline">Мало данных</Badge>;
  if (decision === "no_clear_winner")
    return <Badge variant="outline">Без явного лидера</Badge>;
  if (status === "running")
    return (
      <Badge>
        <Play className="mr-1 h-3 w-3" />
        Запущен
      </Badge>
    );
  if (status === "finished")
    return (
      <Badge variant="outline">
        <CheckCircle2 className="mr-1 h-3 w-3" />
        Завершён
      </Badge>
    );
  if (status === "failed" || status === "stopped")
    return <Badge variant="destructive">Внимание</Badge>;
  return <Badge variant="secondary">Ожидает</Badge>;
}

function normalizeStatus(status: string) {
  const raw = String(status || "").toLowerCase();
  if (raw.includes("running")) return "running";
  if (raw.includes("finish")) return "finished";
  if (raw.includes("failed")) return "failed";
  if (raw.includes("stop")) return "stopped";
  return "pending";
}
