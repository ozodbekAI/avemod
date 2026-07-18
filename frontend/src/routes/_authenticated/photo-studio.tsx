// @ts-nocheck
import { createFileRoute, Link, Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useAccounts } from "@/lib/account-context";
import {
  ensureProjectForNm,
  fetchPhotoCardImages,
  fetchPhotoProjects,
  humanizeProjectStatus,
  photoDisplayUrl,
  type PhotoProject,
} from "@/lib/photo-studio";
import { fetchPortalProducts, type PortalProductRow } from "@/lib/portal";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { PageHeader, PageShell } from "@/components/PageShell";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { EndpointError } from "@/components/EndpointError";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertTriangle,
  ArrowRight,
  ImageOff,
  Loader2,
  MessageSquare,
  PackageOpen,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/photo-studio")({
  component: PhotoStudioRoute,
  errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} />,
});

function PhotoStudioRoute() {
  const location = useLocation();
  if (location.pathname.startsWith("/photo-studio/projects/")) {
    return <Outlet />;
  }
  return <PhotoStudioProjectsPage />;
}

function PhotoStudioProjectsPage() {
  const { activeId } = useAccounts();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search.trim(), 350);

  const projectsQuery = useQuery({
    queryKey: ["photo", "projects", activeId],
    queryFn: () => fetchPhotoProjects(activeId, { limit: 100 }),
    enabled: !!activeId,
    staleTime: 30_000,
  });

  const productsQuery = useQuery({
    queryKey: ["photo", "project-picker-products", activeId, debouncedSearch],
    queryFn: () =>
      fetchPortalProducts(activeId, {
        limit: 80,
        offset: 0,
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
      }),
    enabled: !!activeId && pickerOpen,
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  });

  const projects = useMemo(() => extractProjects(projectsQuery.data), [projectsQuery.data]);
  const productRows = useMemo(
    () => locallyFilterProducts(extractProducts(productsQuery.data), debouncedSearch),
    [productsQuery.data, debouncedSearch],
  );
  const projectByNm = useMemo(() => {
    const map = new Map<string, PhotoProject>();
    for (const project of projects) {
      if (project.nm_id != null) map.set(String(project.nm_id), project);
    }
    return map;
  }, [projects]);

  const createProjectMutation = useMutation({
    mutationFn: (product: PortalProductRow) => {
      if (!activeId) throw new Error("Аккаунт не выбран");
      return ensureProjectForNm({
        accountId: activeId,
        nmId: product.nm_id,
        source: "photo_studio",
        source_action_key: "manual",
      });
    },
    onSuccess: async (project) => {
      setPickerOpen(false);
      setSearch("");
      await queryClient.invalidateQueries({ queryKey: ["photo", "projects", activeId] });
      toast.success("Проект открыт");
      navigate({
        to: "/photo-studio/projects/$projectId",
        params: { projectId: String(project.id) },
      });
    },
    onError: (error: any) => {
      toast.error(error?.message ?? "Не удалось создать проект");
    },
  });

  const projectCount = projects.length;

  return (
    <PageShell>
      <PageHeader
        title="Фотостудия"
        description={
          activeId
            ? projectsQuery.isLoading
              ? "Загружаем проекты фотостудии"
              : projectCount
                ? `Проекты по артикулам WB: ${projectCount}`
                : "Создайте проект из карточки товара"
            : "Выберите аккаунт, чтобы открыть проекты фотостудии"
        }
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => projectsQuery.refetch()}
              disabled={!activeId || projectsQuery.isFetching}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${projectsQuery.isFetching ? "animate-spin" : ""}`} />
              Обновить
            </Button>
            <Button onClick={() => setPickerOpen(true)} disabled={!activeId}>
              <Plus className="h-4 w-4 mr-2" />
              Создать проект
            </Button>
          </div>
        }
      />

      {!activeId ? (
        <NoAccountSelected message="Чтобы работать с фотостудией, выберите WB-аккаунт в верхней панели." />
      ) : projectsQuery.isError ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Не удалось загрузить проекты фотостудии</AlertTitle>
          <AlertDescription>
            {projectsQuery.error instanceof Error ? projectsQuery.error.message : "Проверьте соединение с backend."}
          </AlertDescription>
        </Alert>
      ) : projectsQuery.isLoading ? (
        <ProjectsSkeleton />
      ) : projectCount ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={String(project.id)} project={project} accountId={activeId} />
          ))}
        </div>
      ) : (
        <EmptyProjects onCreate={() => setPickerOpen(true)} />
      )}

      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Выберите карточку WB</DialogTitle>
            <DialogDescription>
              Введите nm_id товара или найдите карточку WB. nm_id для проекта обязателен, для выбранного артикула будет открыт отдельный проект фотостудии со своей историей, фото и чатом.
            </DialogDescription>
          </DialogHeader>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Поиск по nmID, артикулу или названию"
              className="pl-9"
              autoFocus
            />
          </div>

          <div className="max-h-[58vh] overflow-y-auto rounded-md border">
            {productsQuery.isLoading ? (
              <ProductPickerSkeleton />
            ) : productsQuery.isError ? (
              <div className="p-4">
                <Alert variant="destructive">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle>Не удалось загрузить карточки</AlertTitle>
                  <AlertDescription>
                    {productsQuery.error instanceof Error ? productsQuery.error.message : "Backend не вернул список карточек."}
                  </AlertDescription>
                </Alert>
              </div>
            ) : productRows.length ? (
              <div className="divide-y">
                {productRows.map((product) => {
                  const existingProject = projectByNm.get(String(product.nm_id));
                  const disabled = createProjectMutation.isPending;
                  return (
                    <button
                      key={String(product.nm_id)}
                      type="button"
                      className="flex w-full items-center gap-3 p-3 text-left transition-colors hover:bg-muted/60 disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={disabled}
                      onClick={() => createProjectMutation.mutate(product)}
                    >
                      <ProductThumb product={product} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{productTitle(product)}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <span>nmID {product.nm_id}</span>
                          {product.vendor_code ? <span>Артикул {product.vendor_code}</span> : null}
                          {existingProject ? (
                            <Badge variant="outline" className="text-[10px]">
                              Проект уже есть
                            </Badge>
                          ) : null}
                        </div>
                      </div>
                      {createProjectMutation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                      ) : (
                        <ArrowRight className="h-4 w-4 text-muted-foreground" />
                      )}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="flex min-h-40 flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
                <PackageOpen className="h-8 w-8" />
                <div>Карточки не найдены</div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

function ProjectCard({ project, accountId }: { project: PhotoProject; accountId: number | null | undefined }) {
  const queryClient = useQueryClient();
  const cachedDetail = queryClient.getQueryData(["photo", "project", String(project.id), accountId]);
  const initialImage = projectImage(project) ?? projectImage(cachedDetail);
  const fallbackImagesQ = useQuery({
    queryKey: ["photo", "project-card-image", accountId, project.nm_id],
    queryFn: () => fetchPhotoCardImages(accountId, project.nm_id),
    enabled: !!accountId && project.nm_id != null && !initialImage,
    staleTime: 60_000,
  });
  const image = initialImage ?? fallbackImagesQ.data?.[0] ?? null;
  const title = projectTitle(project);
  const status = String(project.status ?? "");

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <Link
          to="/photo-studio/projects/$projectId"
          params={{ projectId: String(project.id) }}
          className="block focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
        >
          <div className="flex gap-4 p-4">
            <div className="h-24 w-24 shrink-0 overflow-hidden rounded-md border bg-muted">
              {image ? (
                <SafePhotoImg src={image} alt={title} className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-muted-foreground">
                  <ImageOff className="h-6 w-6" />
                </div>
              )}
            </div>

            <div className="min-w-0 flex-1 space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-medium">{title}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {project.nm_id != null ? `nmID ${project.nm_id}` : "Без nmID"}
                    {project.vendor_code ? ` · ${project.vendor_code}` : ""}
                  </div>
                </div>
                <Badge variant="outline" className={statusClass(status)}>
                  {humanizeProjectStatus(status)}
                </Badge>
              </div>

              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  <Sparkles className="h-3.5 w-3.5" />
                  {project.versions_count ?? 0} версий
                </span>
                <span className="inline-flex items-center gap-1">
                  <MessageSquare className="h-3.5 w-3.5" />
                  {project.comments_count ?? 0} сообщений
                </span>
              </div>

              <div className="text-xs text-muted-foreground">
                {project.last_activity_at
                  ? `Последняя активность: ${formatDate(project.last_activity_at)}`
                  : project.created_at
                    ? `Создан: ${formatDate(project.created_at)}`
                    : "Откройте проект для работы с фото"}
              </div>
            </div>
          </div>
        </Link>
      </CardContent>
    </Card>
  );
}

function EmptyProjects({ onCreate }: { onCreate: () => void }) {
  return (
    <Card>
      <CardContent className="flex min-h-72 flex-col items-center justify-center gap-4 p-8 text-center">
        <div className="rounded-full bg-primary/10 p-4 text-primary">
          <Sparkles className="h-8 w-8" />
        </div>
        <div>
          <div className="text-lg font-semibold">Проектов пока нет</div>
          <div className="mt-1 max-w-md text-sm text-muted-foreground">
            Создайте проект из карточки WB. У каждого артикула будет отдельная история, изображения и рабочий чат.
          </div>
        </div>
        <Button onClick={onCreate}>
          <Plus className="h-4 w-4 mr-2" />
          Создать проект
        </Button>
      </CardContent>
    </Card>
  );
}

function ProjectsSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, index) => (
        <Card key={index}>
          <CardContent className="flex gap-4 p-4">
            <Skeleton className="h-24 w-24 rounded-md" />
            <div className="flex-1 space-y-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
              <Skeleton className="h-3 w-2/3" />
              <Skeleton className="h-8 w-full" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ProductPickerSkeleton() {
  return (
    <div className="divide-y">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="flex items-center gap-3 p-3">
          <Skeleton className="h-14 w-14 rounded-md" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}

function ProductThumb({ product }: { product: PortalProductRow }) {
  const image = productImage(product);
  const title = productTitle(product);
  return (
    <div className="h-14 w-14 shrink-0 overflow-hidden rounded-md border bg-muted">
      {image ? (
        <SafePhotoImg src={image} alt={title} className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-muted-foreground">
          <ImageOff className="h-4 w-4" />
        </div>
      )}
    </div>
  );
}

function SafePhotoImg({ src, alt, className }: { src: string; alt: string; className?: string }) {
  const displaySrc = photoDisplayUrl(src);
  return (
    <img
      src={displaySrc}
      alt={alt}
      className={className}
      loading="lazy"
      referrerPolicy="no-referrer"
      crossOrigin="anonymous"
    />
  );
}

function extractProjects(data: unknown): PhotoProject[] {
  if (!data) return [];
  if (Array.isArray(data)) return data.filter(isRecordLike) as PhotoProject[];
  const value = data as any;
  if (Array.isArray(value.items)) return value.items.filter(isRecordLike) as PhotoProject[];
  if (Array.isArray(value.projects)) return value.projects.filter(isRecordLike) as PhotoProject[];
  if (Array.isArray(value.data)) return value.data.filter(isRecordLike) as PhotoProject[];
  return [];
}

function extractProducts(data: unknown): PortalProductRow[] {
  if (!data) return [];
  if (Array.isArray(data)) return data.filter(isRecordLike) as PortalProductRow[];
  const value = data as any;
  if (Array.isArray(value.items)) return value.items.filter(isRecordLike) as PortalProductRow[];
  if (Array.isArray(value.products)) return value.products.filter(isRecordLike) as PortalProductRow[];
  if (Array.isArray(value.data)) return value.data.filter(isRecordLike) as PortalProductRow[];
  return [];
}

function isRecordLike(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function locallyFilterProducts(rows: PortalProductRow[], search: string): PortalProductRow[] {
  if (!search) return rows;
  const query = search.toLowerCase();
  return rows.filter((row) => {
    const title = productTitle(row).toLowerCase();
    return (
      String(row.nm_id).includes(query) ||
      title.includes(query) ||
      (row.vendor_code ?? "").toLowerCase().includes(query)
    );
  });
}

function projectTitle(project: PhotoProject | null | undefined): string {
  return (
    project?.product_name ||
    (project as any)?.title ||
    (project as any)?.name ||
    project?.vendor_code ||
    (project?.nm_id != null ? `Товар ${project.nm_id}` : `Проект ${project?.id ?? "без ID"}`)
  );
}

function productTitle(product: PortalProductRow | null | undefined): string {
  return (
    product?.name ||
    (product as any)?.title ||
    (product as any)?.product_name ||
    product?.vendor_code ||
    `Товар ${product?.nm_id ?? "без nmID"}`
  );
}

function projectImage(project: unknown): string | null {
  const value = ((project as any)?.project ?? project) as any;
  if (!isRecordLike(value)) return null;
  return firstString(
    value?.approved_thumbnail,
    value?.preferred_thumbnail,
    value?.thumbnail,
    firstArrayImage(value?.photos),
    firstArrayImage(value?.assets),
    value?.image_url,
    value?.photo_url,
  );
}

function productImage(product: PortalProductRow | null | undefined): string | null {
  if (!isRecordLike(product)) return null;
  return firstString(
    (product as any).thumbnail,
    (product as any).thumbnail_url,
    (product as any).display_photo_url,
    (product as any).proxy_photo_url,
    (product as any).main_photo_url,
    (product as any).image_url,
    (product as any).photo_url,
    (product as any).photo,
    firstArrayImage((product as any).photos),
    firstArrayImage((product as any).images),
  );
}

function firstArrayImage(value: unknown): string | null {
  if (!Array.isArray(value)) return null;
  for (const item of value) {
    if (typeof item === "string" && item) return item;
    const url = firstString(
      (item as any)?.big,
      (item as any)?.canonical_url,
      (item as any)?.url,
      (item as any)?.full,
      (item as any)?.photo,
      (item as any)?.source_url,
      (item as any)?.src,
      (item as any)?.c516x688,
      (item as any)?.square,
      (item as any)?.c246x328,
      (item as any)?.tm,
      (item as any)?.thumbnail,
      (item as any)?.preview,
    );
    if (url) return url;
  }
  return null;
}

function firstString(...values: Array<unknown>): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

function statusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (["approved", "completed", "done"].includes(normalized)) return "bg-success/10 text-success border-success/30";
  if (["rejected", "failed"].includes(normalized)) return "bg-destructive/10 text-destructive border-destructive/30";
  if (["in_progress", "running", "queued", "draft"].includes(normalized)) return "bg-primary/10 text-primary border-primary/30";
  return "bg-muted text-muted-foreground border-border";
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
