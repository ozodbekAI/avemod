import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useAccounts } from "@/lib/account-context";
import {
  applyVersionToWb,
  saveProjectCardPhotosToWb,
  fetchPhotoCardImages,
  fetchPhotoProject,
  fetchPhotoSettings,
  fetchPhotoStatus,
  importWbAssets,
  uploadProjectAsset,
  createPhotoJob,
  cancelPhotoJob,
  retryPhotoJob,
  createPhotoVersion,
  fetchPhotoAssetDownloadUrl,
  createPhotoVersionExperiment,
  preferVersion,
  approveVersion,
  rejectVersion,
  addProjectComment,
  recordManualWbUpdate,
  photoDisplayUrl,
  humanizeProjectStatus,
  humanizeJobState,
  humanizeOperation,
  isTerminalJob,
  generationStateOf,
  type PhotoAsset,
  type PhotoVersion,
  type PhotoJob,
} from "@/lib/photo-studio";
import { PageShell, PageHeader } from "@/components/PageShell";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { EndpointError } from "@/components/EndpointError";
import {
  AlertTriangle,
  ChevronLeft,
  ImageOff,
  Upload,
  Download,
  Sparkles,
  Send,
  Star,
  CheckCircle2,
  XCircle,
  MessageSquarePlus,
  RefreshCcw,
  ImagePlus,
  Info,
  GripVertical,
} from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute(
  "/_authenticated/photo-studio/projects/$projectId",
)({
  component: PhotoProjectWorkspace,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

const PHOTO_STUDIO_EXPERIMENT_LABEL = "Отслеживать эффект 14 дней";
const PHOTO_STUDIO_DOWNLOAD_CONTRACT =
  "fetchPhotoAssetDownloadUrl(approvedVersion.asset_id";

// Helpers to safely extract collections from backend payload (shapes may vary).
function pickArr<T = any>(d: any, ...keys: string[]): T[] {
  for (const k of keys) {
    const v = d?.[k];
    if (Array.isArray(v)) return v as T[];
    if (Array.isArray(v?.items)) return v.items as T[];
  }
  return [];
}

function isWbAsset(asset: PhotoAsset | null | undefined): boolean {
  if (!asset) return false;
  const source = String(asset.source ?? "").toLowerCase();
  const sourceType = String(asset.source_type ?? "").toLowerCase();
  const kind = String(asset.kind ?? "").toLowerCase();
  return (
    source === "wb" ||
    sourceType === "wb" ||
    sourceType === "wb_sync" ||
    kind === "source_wb"
  );
}

function Thumb({
  src,
  alt,
  big,
}: {
  src?: string | null;
  alt: string;
  big?: boolean;
}) {
  const cls = big ? "w-full max-w-md aspect-square" : "w-20 h-20";
  if (!src) {
    return (
      <div
        className={`${cls} rounded border bg-muted flex items-center justify-center text-muted-foreground`}
      >
        <ImageOff className="h-5 w-5" />
      </div>
    );
  }
  return (
    <SafePhotoImage
      src={src}
      alt={alt}
      className={`${cls} rounded border object-cover bg-muted`}
    />
  );
}

function SafePhotoImage({
  src,
  alt,
  className,
}: {
  src?: string | null;
  alt: string;
  className?: string;
}) {
  const displaySrc = photoDisplayUrl(src);
  const [failed, setFailed] = useState(!displaySrc);
  if (!displaySrc || failed) {
    return (
      <div
        className={`${className ?? ""} flex items-center justify-center bg-muted text-muted-foreground`}
        aria-label={alt}
      >
        <ImageOff className="h-5 w-5" />
      </div>
    );
  }
  return (
    <img
      src={displaySrc}
      alt=""
      aria-label={alt}
      loading="lazy"
      className={className}
      onError={() => setFailed(true)}
    />
  );
}

function AssetTile({
  asset,
  selected,
  onSelect,
  action,
}: {
  asset: PhotoAsset;
  selected?: boolean;
  onSelect?: () => void;
  action?: ReactNode;
}) {
  const label =
    asset.original_file_name ?? asset.filename ?? `Asset ${asset.id}`;
  const src = asset.thumbnail ?? asset.url ?? asset.source_url ?? null;
  const source = asset.source ?? asset.source_type;
  return (
    <div
      className={`relative rounded border p-1 text-left transition-colors hover:bg-accent ${
        selected ? "ring-2 ring-primary" : ""
      }`}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className="block text-left"
      >
        <Thumb src={src} alt={label} />
        <div className="mt-1 text-[10px] text-muted-foreground truncate max-w-[80px]">
          {isWbAsset(asset) ? "WB" : source === "generation" ? "ИИ" : "Загруж."}
          {asset.width && asset.height
            ? ` • ${asset.width}×${asset.height}`
            : ""}
        </div>
      </button>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

function VersionCard({
  v,
  source,
  projectId,
  accountId,
  publishEnabled,
  onCompare,
}: {
  v: PhotoVersion;
  source: PhotoAsset | null;
  projectId: number | string;
  accountId: number;
  publishEnabled: boolean;
  onCompare: (v: PhotoVersion) => void;
}) {
  const qc = useQueryClient();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [approveOpen, setApproveOpen] = useState(false);

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["photo", "project", projectId] });

  const preferMut = useMutation({
    mutationFn: () => preferVersion(projectId, v.id, accountId),
    onSuccess: () => {
      toast.success("Версия отмечена как предпочтительная");
      invalidate();
    },
    onError: (e: any) => toast.error(e?.message ?? "Ошибка"),
  });
  const approveMut = useMutation({
    mutationFn: () => approveVersion(projectId, v.id, accountId),
    onSuccess: () => {
      toast.success("Версия одобрена");
      setApproveOpen(false);
      invalidate();
    },
    onError: (e: any) => toast.error(e?.message ?? "Ошибка"),
  });
  const rejectMut = useMutation({
    mutationFn: () =>
      rejectVersion(projectId, v.id, accountId, rejectReason.trim()),
    onSuccess: () => {
      toast.success("Версия отклонена");
      setRejectOpen(false);
      setRejectReason("");
      invalidate();
    },
    onError: (e: any) => toast.error(e?.message ?? "Ошибка"),
  });
  const downloadMut = useMutation({
    mutationFn: () => fetchPhotoAssetDownloadUrl(v.asset_id!, accountId),
    onSuccess: (r) => {
      if (r?.url) window.open(r.url, "_blank", "noopener,noreferrer");
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось подготовить ссылку"),
  });

  const status = String(v.status ?? "").toLowerCase();
  const isPreferred = Boolean(v.is_preferred || status === "preferred");
  const isApproved = Boolean(v.is_approved || status === "approved");
  const versionNumber = v.number ?? v.version_number ?? v.id;
  return (
    <Card>
      <CardContent className="p-3 flex gap-3">
        <Thumb
          src={v.thumbnail ?? v.url ?? source?.source_url ?? null}
          alt={`Версия ${versionNumber}`}
        />
        <div className="flex-1 min-w-0 space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="text-[10px]">
              №{versionNumber}
            </Badge>
            {isPreferred && (
              <Badge
                className="text-[10px] bg-primary/10 text-primary border-primary/30"
                variant="outline"
              >
                <Star className="h-2.5 w-2.5 mr-1" />
                Предпочтительная
              </Badge>
            )}
            {isApproved && (
              <Badge
                className="text-[10px] bg-success/10 text-success border-success/30"
                variant="outline"
              >
                Одобрена
              </Badge>
            )}
            {status === "rejected" && (
              <Badge
                variant="outline"
                className="text-[10px] bg-destructive/10 text-destructive border-destructive/30"
              >
                Отклонена
              </Badge>
            )}
            {v.operation && (
              <Badge variant="outline" className="text-[10px]">
                {humanizeOperation(v.operation)}
              </Badge>
            )}
            {v.source && (
              <Badge variant="outline" className="text-[10px]">
                {v.source === "generation" ? "ИИ" : "Загрузка"}
              </Badge>
            )}
          </div>
          {(v.rejected_reason || v.rejection_reason) && (
            <div className="text-[11px] text-destructive">
              Причина: {v.rejected_reason ?? v.rejection_reason}
            </div>
          )}
          {v.created_at && (
            <div className="text-[11px] text-muted-foreground">
              {new Date(v.created_at).toLocaleString("ru-RU")}
            </div>
          )}
          <div className="flex flex-wrap gap-1.5 pt-1">
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={() => onCompare(v)}
            >
              Сравнить
            </Button>
            {!isPreferred && status !== "rejected" && (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={() => preferMut.mutate()}
                disabled={preferMut.isPending}
              >
                <Star className="h-3 w-3 mr-1" /> Сделать предпочтительной
              </Button>
            )}
            {!isApproved && status !== "rejected" && (
              <>
                <Button
                  size="sm"
                  variant="default"
                  className="h-7 text-xs"
                  onClick={() => setApproveOpen(true)}
                >
                  <CheckCircle2 className="h-3 w-3 mr-1" /> Одобрить
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  onClick={() => setRejectOpen(true)}
                >
                  <XCircle className="h-3 w-3 mr-1" /> Отклонить
                </Button>
              </>
            )}
            {isApproved && v.asset_id != null && (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={() => downloadMut.mutate()}
                disabled={downloadMut.isPending}
              >
                <Download className="h-3 w-3 mr-1" /> Скачать одобренную версию
              </Button>
            )}
            {publishEnabled && isApproved && (
              <Badge variant="outline" className="text-[10px]">
                <Info className="h-3 w-3 mr-1" /> Загрузка в WB — вручную
              </Badge>
            )}
          </div>
          {source && (
            <div className="text-[10px] text-muted-foreground pt-1">
              Исходник: #{source.id} ({source.source ?? "?"})
            </div>
          )}
        </div>
      </CardContent>

      <Dialog open={approveOpen} onOpenChange={setApproveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Одобрить версию?</DialogTitle>
            <DialogDescription>
              Версия будет отмечена как готовая. Она не будет автоматически
              загружена в WB.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproveOpen(false)}>
              Отмена
            </Button>
            <Button
              onClick={() => approveMut.mutate()}
              disabled={approveMut.isPending}
            >
              Одобрить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Отклонить версию</DialogTitle>
            <DialogDescription>
              Укажите причину — это обязательно.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Причина отклонения"
            rows={3}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectOpen(false)}>
              Отмена
            </Button>
            <Button
              variant="destructive"
              disabled={!rejectReason.trim() || rejectMut.isPending}
              onClick={() => rejectMut.mutate()}
            >
              Отклонить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function CompareView({
  left,
  right,
}: {
  left: PhotoAsset | PhotoVersion | null;
  right: PhotoVersion | null;
}) {
  if (!right) return null;
  const leftSrc =
    (left as any)?.url ??
    (left as any)?.thumbnail ??
    (left as any)?.source_url ??
    null;
  const rightSrc = right.url ?? right.thumbnail ?? null;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div>
        <div className="text-xs uppercase text-muted-foreground mb-1">
          Исходник
        </div>
        <Thumb src={leftSrc} alt="Исходник" big />
      </div>
      <div>
        <div className="text-xs uppercase text-muted-foreground mb-1">
          Версия №{right.number ?? right.version_number ?? right.id}
        </div>
        <Thumb
          src={rightSrc}
          alt={`Версия ${right.number ?? right.version_number ?? right.id}`}
          big
        />
        {right.warnings && right.warnings.length > 0 && (
          <ul className="text-[11px] text-warning mt-2 space-y-0.5">
            {right.warnings.map((w, i) => (
              <li key={i}>• {w}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function photoProjectTitle(project: any, projectId: number | string): string {
  const raw = String(
    project?.product_name ?? project?.title ?? `Проект #${projectId}`,
  );
  return raw.trim().toLowerCase() === "photo studio chat"
    ? "Проект фотостудии"
    : raw;
}

function UploadZone({
  projectId,
  accountId,
  onUploaded,
  allowedFormats,
  maxMb,
}: {
  projectId: number | string;
  accountId: number;
  onUploaded: () => void;
  allowedFormats?: string[];
  maxMb?: number;
}) {
  const [progress, setProgress] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const validate = (f: File): string | null => {
    if (maxMb && f.size > maxMb * 1024 * 1024) return "Файл слишком большой";
    if (allowedFormats && allowedFormats.length) {
      const ok = allowedFormats.some((fmt) => {
        const normalized = fmt.toLowerCase();
        const ext = normalized.includes("/")
          ? normalized.split("/").pop()?.replace("jpeg", "jpg")
          : normalized.replace(/^\./, "");
        return (
          f.type.toLowerCase() === normalized ||
          Boolean(ext && f.name.toLowerCase().endsWith(`.${ext}`))
        );
      });
      if (!ok) return "Неверный формат";
    }
    return null;
  };

  const handle = async (file: File) => {
    setErr(null);
    const v = validate(file);
    if (v) {
      setErr(v);
      return;
    }
    try {
      setProgress(0);
      await uploadProjectAsset(projectId, accountId, file, (p) =>
        setProgress(p),
      );
      setProgress(null);
      toast.success("Изображение загружено");
      onUploaded();
    } catch (e: any) {
      setProgress(null);
      setErr(e?.message ?? "Ошибка загрузки");
    }
  };

  return (
    <div
      className="rounded-md border border-dashed p-4 text-center bg-muted/30"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const f = e.dataTransfer.files?.[0];
        if (f) void handle(f);
      }}
    >
      <ImagePlus className="h-6 w-6 mx-auto mb-1 text-muted-foreground" />
      <div className="text-sm font-medium">
        Перетащите файл или выберите вручную
      </div>
      <div className="text-[11px] text-muted-foreground mt-0.5">
        {allowedFormats?.length
          ? `Форматы: ${allowedFormats.join(", ")}. `
          : ""}
        {maxMb ? `До ${maxMb} МБ.` : ""}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={allowedFormats?.join(",")}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handle(f);
          e.target.value = "";
        }}
      />
      <div className="mt-2 flex items-center justify-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => inputRef.current?.click()}
          disabled={progress != null}
        >
          <Upload className="h-3.5 w-3.5 mr-1" /> Выбрать файл
        </Button>
      </div>
      {progress != null && (
        <div className="mt-2 text-xs text-muted-foreground">
          Загрузка… {progress}%
        </div>
      )}
      {err && (
        <Alert variant="destructive" className="mt-2 text-left">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{err}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}

function GenerateBlock({
  projectId,
  accountId,
  assets,
  supportedOps,
  generationOk,
  onJobCreated,
}: {
  projectId: number | string;
  accountId: number;
  assets: PhotoAsset[];
  supportedOps: string[];
  generationOk: boolean;
  onJobCreated: () => void;
}) {
  const [assetId, setAssetId] = useState<string>(
    assets[0] ? String(assets[0].id) : "",
  );
  const [operation, setOperation] = useState<string>(supportedOps[0] ?? "");
  const [brief, setBrief] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if (!assetId && assets[0]) setAssetId(String(assets[0].id));
  }, [assets, assetId]);

  const createMut = useMutation({
    mutationFn: () =>
      createPhotoJob(projectId, {
        account_id: accountId,
        asset_id: assetId,
        operation,
        brief: brief.trim() || null,
      }),
    onSuccess: () => {
      toast.success("Задача поставлена в очередь");
      setConfirmOpen(false);
      onJobCreated();
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось создать задачу"),
  });

  if (!generationOk) {
    return (
      <Alert>
        <Sparkles className="h-4 w-4" />
        <AlertTitle>ИИ-обработка не подключена</AlertTitle>
        <AlertDescription>
          Можно загрузить готовую версию вручную через панель «Исходники».
        </AlertDescription>
      </Alert>
    );
  }
  if (supportedOps.length === 0) {
    return (
      <Alert>
        <Sparkles className="h-4 w-4" />
        <AlertTitle>Операции не настроены</AlertTitle>
        <AlertDescription>
          Бэкенд не сообщил доступные операции.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="text-sm font-semibold flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" /> Создать версию
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <div>
            <div className="text-[11px] uppercase text-muted-foreground mb-1">
              Исходник
            </div>
            <Select value={assetId} onValueChange={setAssetId}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Выберите" />
              </SelectTrigger>
              <SelectContent>
                {assets.map((a) => (
                  <SelectItem
                    key={String(a.id)}
                    value={String(a.id)}
                    className="text-xs"
                  >
                    #{a.id}{" "}
                    {(a.original_file_name ?? a.filename)
                      ? `— ${a.original_file_name ?? a.filename}`
                      : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <div className="text-[11px] uppercase text-muted-foreground mb-1">
              Операция
            </div>
            <Select value={operation} onValueChange={setOperation}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {supportedOps.map((op) => (
                  <SelectItem key={op} value={op} className="text-xs">
                    {humanizeOperation(op)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase text-muted-foreground mb-1">
            Что нужно изменить / сохранить
          </div>
          <Textarea
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            rows={3}
            placeholder="Фон, композиция, стиль, формат…"
          />
        </div>
        <div className="flex justify-end">
          <Button
            size="sm"
            disabled={!assetId || !operation}
            onClick={() => setConfirmOpen(true)}
          >
            <Sparkles className="h-3.5 w-3.5 mr-1" /> Создать вариант
          </Button>
        </div>

        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Подтвердите задачу</DialogTitle>
              <DialogDescription>
                Будет создана задача «{humanizeOperation(operation)}». Результат
                появится после обработки.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                Отмена
              </Button>
              <Button
                onClick={() => createMut.mutate()}
                disabled={createMut.isPending}
              >
                Запустить
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}

function JobsBlock({
  jobs,
  accountId,
  refetchInterval,
}: {
  jobs: PhotoJob[];
  accountId: number;
  refetchInterval: () => void;
}) {
  const stateOf = (j: PhotoJob) => j.status ?? j.state;
  const activeJobs = jobs.filter((j) => !isTerminalJob(stateOf(j)));
  if (jobs.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="text-xs uppercase text-muted-foreground">Задачи</div>
      {jobs.slice(0, 5).map((j) => (
        <Card key={String(j.id)}>
          <CardContent className="p-3 flex items-center gap-3">
            <div className="flex-1 text-sm">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline" className="text-[10px]">
                  {humanizeJobState(stateOf(j))}
                </Badge>
                {(j.job_type ?? j.operation) && (
                  <Badge variant="outline" className="text-[10px]">
                    {humanizeOperation(j.job_type ?? j.operation)}
                  </Badge>
                )}
                {(j.progress_percent ?? j.progress) != null &&
                  !isTerminalJob(stateOf(j)) && (
                    <span className="text-[11px] text-muted-foreground">
                      {j.progress_percent ?? j.progress}%
                    </span>
                  )}
              </div>
              {(j.error_message ?? j.error) && (
                <div className="text-[11px] text-destructive mt-0.5">
                  {j.error_message ?? j.error}
                </div>
              )}
              {j.message && !(j.error_message ?? j.error) && (
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  {j.message}
                </div>
              )}
            </div>
            {!isTerminalJob(stateOf(j)) && (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={async () => {
                  try {
                    await cancelPhotoJob(j.id, accountId);
                    toast.success("Отменено");
                    refetchInterval();
                  } catch (e: any) {
                    toast.error(e?.message ?? "Ошибка");
                  }
                }}
              >
                Отменить
              </Button>
            )}
            {["failed", "cancelled", "not_configured"].includes(
              String(stateOf(j)),
            ) && (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={async () => {
                  try {
                    await retryPhotoJob(j.id, accountId);
                    toast.success("Повтор поставлен в очередь");
                    refetchInterval();
                  } catch (e: any) {
                    toast.error(e?.message ?? "Ошибка");
                  }
                }}
              >
                Повторить
              </Button>
            )}
          </CardContent>
        </Card>
      ))}
      {activeJobs.length > 0 && (
        <div className="text-[10px] text-muted-foreground">
          Обновление каждые ~5 секунд, пока есть активные задачи.
        </div>
      )}
    </div>
  );
}

function PhotoChatPanel({
  projectId,
  accountId,
  assets,
  jobs,
  comments,
  generationOk,
  supportedOps,
  onChanged,
}: {
  projectId: number | string;
  accountId: number;
  assets: PhotoAsset[];
  jobs: PhotoJob[];
  comments: any[];
  generationOk: boolean;
  supportedOps: string[];
  onChanged: () => void;
}) {
  const [assetId, setAssetId] = useState<string>(
    assets[0] ? String(assets[0].id) : "",
  );
  const [message, setMessage] = useState("");
  const [operation, setOperation] = useState<string>(
    supportedOps.includes("background_replace")
      ? "background_replace"
      : (supportedOps[0] ?? "variant"),
  );

  useEffect(() => {
    if (!assetId && assets[0]) setAssetId(String(assets[0].id));
  }, [assets, assetId]);

  useEffect(() => {
    if (!supportedOps.includes(operation) && supportedOps[0])
      setOperation(supportedOps[0]);
  }, [operation, supportedOps]);

  const sendMut = useMutation({
    mutationFn: async (quickPrompt?: string) => {
      const text = (quickPrompt ?? message).trim();
      if (!text) throw new Error("Напишите, что нужно сделать");
      if (!generationOk) throw new Error("ИИ-обработка не подключена");
      if (!assetId)
        throw new Error("Сначала импортируйте или загрузите исходное фото");
      await addProjectComment(projectId, accountId, text);
      return createPhotoJob(projectId, {
        account_id: accountId,
        asset_id: assetId,
        operation,
        brief: text,
      });
    },
    onSuccess: () => {
      toast.success("Сообщение отправлено, задача запущена");
      setMessage("");
      onChanged();
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось отправить"),
  });

  const quick = [
    {
      label: "Сменить фон",
      op: "background_replace",
      prompt:
        "Заменить фон на чистый светлый e-commerce фон, товар оставить без изменений.",
    },
    {
      label: "Улучшить качество",
      op: "enhance",
      prompt: "Улучшить резкость, свет и цвет, товар оставить без изменений.",
    },
    {
      label: "Создать вариант",
      op: "variant",
      prompt:
        "Создать готовый для карточки вариант фото, сохранив товар без изменений.",
    },
  ].filter(
    (item) => supportedOps.includes(item.op) || supportedOps.length === 0,
  );

  const chatItems = [
    ...comments.map((c) => ({
      id: `c-${c.id ?? c.created_at ?? Math.random()}`,
      role: c.author_type === "system" ? "assistant" : "user",
      text: c.text ?? c.message ?? "",
      at: c.created_at,
    })),
    ...jobs.slice(0, 8).map((j) => ({
      id: `j-${j.id}`,
      role: "assistant",
      text: `${humanizeOperation(j.job_type ?? j.operation)}: ${humanizeJobState(j.status ?? j.state)}${j.error_message || j.error ? ` — ${j.error_message ?? j.error}` : ""}`,
      at: j.created_at,
    })),
  ]
    .filter((item) => item.text)
    .sort((a, b) => String(a.at ?? "").localeCompare(String(b.at ?? "")));

  return (
    <div className="flex h-full min-h-[420px] flex-col bg-background lg:min-h-[calc(100vh-46px)]">
      <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b px-4">
        <div className="flex min-w-0 items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <div className="truncate text-sm font-semibold">ИИ-фотостудия</div>
          <Badge
            variant="outline"
            className="max-w-44 truncate bg-primary/5 text-[11px] text-primary"
          >
            {assets[0]?.filename ?? assets[0]?.original_file_name ?? "Проект"}
          </Badge>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge
            variant="outline"
            className="h-8 rounded-full px-3 text-[11px]"
          >
            Модель
          </Badge>
          <Select value={operation} onValueChange={setOperation}>
            <SelectTrigger className="h-8 w-[170px] rounded-full text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(supportedOps.length
                ? supportedOps
                : ["background_replace", "enhance", "variant"]
              ).map((op) => (
                <SelectItem key={op} value={op} className="text-xs">
                  {humanizeOperation(op)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Badge
            variant="outline"
            className="h-8 rounded-full px-3 text-[11px]"
          >
            {generationOk ? "ИИ включён" : "ИИ не подключён"}
          </Badge>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto bg-muted/10 px-4 py-5">
        <div className="mx-auto flex max-w-5xl flex-col gap-4">
          {chatItems.length === 0 ? (
            <div className="rounded-xl border border-dashed bg-background p-4">
              <div className="flex items-start gap-3">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold">
                    Выберите действие для первого варианта
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Можно сразу улучшить фон, резкость или создать новый вариант
                    для карточки.
                  </div>
                </div>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-3">
                {quick.map((item) => (
                  <Button
                    key={item.label}
                    type="button"
                    variant="outline"
                    className="h-auto justify-start whitespace-normal rounded-lg px-3 py-2 text-left text-xs"
                    disabled={sendMut.isPending || !generationOk || !assetId}
                    onClick={() => {
                      setOperation(item.op);
                      sendMut.mutate(item.prompt);
                    }}
                  >
                    <Sparkles className="mr-2 h-3.5 w-3.5 shrink-0" />
                    {item.label}
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            chatItems.map((item) => (
              <div
                key={item.id}
                className={`flex ${item.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div className="flex max-w-[84%] items-start gap-2">
                  {item.role !== "user" && (
                    <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                      <MessageSquarePlus className="h-4 w-4" />
                    </div>
                  )}
                  <div>
                    <div
                      className={`rounded-2xl px-4 py-3 text-sm shadow-sm ${
                        item.role === "user"
                          ? "bg-primary text-primary-foreground"
                          : "border bg-background text-foreground"
                      }`}
                    >
                      {item.text}
                    </div>
                    {item.at && (
                      <div
                        className={`mt-1 text-[11px] text-muted-foreground ${item.role === "user" ? "text-right" : ""}`}
                      >
                        {new Date(item.at).toLocaleTimeString("ru-RU", {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </div>
                    )}
                  </div>
                  {item.role === "user" && (
                    <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                      <Send className="h-4 w-4" />
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="shrink-0 border-t bg-background px-4 py-3">
        <div className="mx-auto max-w-5xl space-y-2">
          {chatItems.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              {quick.map((item) => (
                <Button
                  key={item.label}
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-8 rounded-full text-xs"
                  disabled={sendMut.isPending || !generationOk || !assetId}
                  onClick={() => {
                    setOperation(item.op);
                    sendMut.mutate(item.prompt);
                  }}
                >
                  <Sparkles className="h-3.5 w-3.5 mr-1" /> {item.label}
                </Button>
              ))}
              <Select value={assetId} onValueChange={setAssetId}>
                <SelectTrigger className="ml-auto h-8 w-[190px] rounded-full text-xs">
                  <SelectValue placeholder="Фото" />
                </SelectTrigger>
                <SelectContent>
                  {assets.map((a) => (
                    <SelectItem
                      key={String(a.id)}
                      value={String(a.id)}
                      className="text-xs"
                    >
                      #{a.id}{" "}
                      {isWbAsset(a)
                        ? "WB"
                        : a.source_type === "ai"
                          ? "ИИ"
                          : "загрузка"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="flex items-end gap-2">
            <Button
              variant="outline"
              size="icon"
              className="h-11 w-11 shrink-0 rounded-full"
              disabled
            >
              <Upload className="h-4 w-4" />
            </Button>
            <Textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={1}
              placeholder="Напишите, что хотите сделать..."
              className="min-h-11 flex-1 resize-none rounded-2xl bg-muted/50 px-4 py-3"
            />
            <Button
              className="h-11 w-11 shrink-0 rounded-full p-0"
              disabled={
                sendMut.isPending ||
                !message.trim() ||
                !generationOk ||
                !assetId
              }
              onClick={() => sendMut.mutate(undefined)}
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function PhotoProjectWorkspace() {
  const { projectId } = Route.useParams();
  const { activeId } = useAccounts();
  const qc = useQueryClient();
  const [compare, setCompare] = useState<{
    left: PhotoAsset | null;
    right: PhotoVersion | null;
  }>({ left: null, right: null });
  const [manualOpen, setManualOpen] = useState(false);
  const [dragOverSlot, setDragOverSlot] = useState<number | null>(null);
  const autoImportAttemptedRef = useRef(false);

  const statusQ = useQuery({
    queryKey: ["photo", "status", activeId],
    queryFn: () => fetchPhotoStatus(activeId),
    enabled: !!activeId,
    staleTime: 60_000,
  });
  const settingsQ = useQuery({
    queryKey: ["photo", "settings", activeId],
    queryFn: () => fetchPhotoSettings(activeId),
    enabled: !!activeId,
    staleTime: 60_000,
  });
  const projectQ = useQuery({
    queryKey: ["photo", "project", projectId, activeId],
    queryFn: () => fetchPhotoProject(projectId, activeId),
    enabled: !!activeId,
    staleTime: 15_000,
  });

  const data = projectQ.data ?? {};
  const project = (data?.project ?? data) as any;
  const projectNmId = project?.nm_id ?? null;
  const cardPhotosQ = useQuery({
    queryKey: ["photo", "card-images", activeId, projectNmId],
    queryFn: () => fetchPhotoCardImages(activeId, projectNmId),
    enabled: !!activeId && projectNmId != null,
    staleTime: 60_000,
  });
  const assets = pickArr<PhotoAsset>(
    data,
    "assets",
    "sources",
    "source_assets",
  );
  const versions = pickArr<PhotoVersion>(data, "versions");
  const jobs = pickArr<PhotoJob>(data, "jobs");
  const comments = pickArr<any>(data, "messages", "comments");
  const history = pickArr<any>(data, "history", "events", "result_history");

  const hasActiveJob = jobs.some((j) => !isTerminalJob(j.status ?? j.state));
  const projectKey = useMemo(
    () => ["photo", "project", projectId, activeId] as const,
    [activeId, projectId],
  );

  // Re-poll while a job is active.
  useEffect(() => {
    if (!hasActiveJob) return;
    const t = setInterval(
      () => qc.invalidateQueries({ queryKey: projectKey }),
      5000,
    );
    return () => clearInterval(t);
  }, [hasActiveJob, projectKey, qc]);

  const importMut = useMutation({
    mutationFn: () => importWbAssets(projectId, activeId!),
    onSuccess: (r) => {
      toast.success(
        r?.imported != null
          ? `Импортировано: ${r.imported}`
          : "Импорт выполнен",
      );
      qc.invalidateQueries({ queryKey: projectKey });
      qc.invalidateQueries({ queryKey: ["photo", "projects", activeId] });
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось импортировать"),
  });
  const createVersionMut = useMutation({
    mutationFn: (asset: PhotoAsset) =>
      createPhotoVersion(projectId, activeId!, {
        asset_id: asset.id,
        label: isWbAsset(asset) ? "Исходник WB" : "Ручная загрузка",
        change_summary: isWbAsset(asset)
          ? "Версия создана из исходного изображения WB"
          : "Версия создана из загруженного изображения",
      }),
    onSuccess: () => {
      toast.success("Версия создана");
      qc.invalidateQueries({ queryKey: projectKey });
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось создать версию"),
  });
  const [manualDate, setManualDate] = useState<string>(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [manualComment, setManualComment] = useState<string>("");
  const manualMut = useMutation({
    mutationFn: () =>
      recordManualWbUpdate(projectId, activeId!, {
        applied_at: manualDate,
        comment: manualComment.trim(),
      }),
    onSuccess: () => {
      toast.success("Зафиксировано: вы обновили изображение в WB вручную");
      setManualOpen(false);
      setManualComment("");
      qc.invalidateQueries({ queryKey: projectKey });
    },
    onError: (e: any) => toast.error(e?.message ?? "Ошибка"),
  });
  const experimentMut = useMutation({
    mutationFn: () =>
      createPhotoVersionExperiment(projectId, approvedVersion!.id, activeId!, {
        hypothesis:
          "Одобренное фото может улучшить конверсию заказа без ухудшения выручки.",
        primary_metric: "conversion_rate",
        secondary_metrics: ["revenue", "orders_count"],
        guardrail_metrics: ["stockout_days", "ads_spend"],
        baseline_days: 7,
        post_days: 14,
      }),
    onSuccess: () => {
      toast.success(
        "Эксперимент создан: baseline 7 дней, сбор после изменения 14 дней",
      );
      qc.invalidateQueries({ queryKey: projectKey });
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось создать эксперимент"),
  });
  const applyWbMut = useMutation({
    mutationFn: ({
      versionId,
      photoNumber,
    }: {
      versionId: number | string;
      photoNumber: number;
    }) => applyVersionToWb(projectId, versionId, activeId!, photoNumber),
    onSuccess: () => {
      toast.success("Фото сохранено в WB");
      qc.invalidateQueries({ queryKey: projectKey });
      qc.invalidateQueries({ queryKey: ["photo", "projects", activeId] });
      qc.invalidateQueries({
        queryKey: ["photo", "card-images", activeId, projectNmId],
      });
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось сохранить в WB"),
  });
  const saveCardPhotosMut = useMutation({
    mutationFn: (photos: string[]) =>
      saveProjectCardPhotosToWb(projectId, activeId!, photos),
    onSuccess: (result) => {
      toast.success(
        result?.matched === false
          ? "Порядок отправлен в WB, проверка ещё обновляется"
          : "Порядок фото сохранён в WB",
      );
      qc.invalidateQueries({ queryKey: projectKey });
      qc.invalidateQueries({ queryKey: ["photo", "projects", activeId] });
      qc.invalidateQueries({
        queryKey: ["photo", "card-images", activeId, projectNmId],
      });
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось сохранить порядок фото"),
  });

  const wbAssets = assets.filter(isWbAsset);
  const userAssets = assets.filter((a) => !isWbAsset(a));
  const cardPhotoUrls = cardPhotosQ.data ?? [];
  const leftPhotos = [
    ...wbAssets.map((asset, index) => ({
      key: `asset-${asset.id}`,
      url: asset.thumbnail ?? asset.url ?? asset.source_url ?? "",
      asset,
      index,
    })),
    ...cardPhotoUrls
      .filter(
        (url) =>
          !wbAssets.some((asset) =>
            [asset.thumbnail, asset.url, asset.source_url].includes(url),
          ),
      )
      .map((url, index) => ({
        key: `card-${url}`,
        url,
        asset: null,
        index: wbAssets.length + index,
      })),
  ].filter((item) => item.url);
  const generation = generationStateOf(statusQ.data ?? null);
  const generationOk = generation === "ok";
  const supportedOps = (settingsQ.data?.generation?.operations ??
    settingsQ.data?.supported_operations ??
    (settingsQ.data?.generation_enabled && settingsQ.data?.default_provider
      ? ["remove_background", "background_replace", "enhance", "variant"]
      : [])) as string[];
  const publishEnabled =
    settingsQ.data?.external_apply_enabled === true ||
    settingsQ.data?.external_apply === true;
  const allowedFormats = settingsQ.data?.allowed_mime_types ??
    settingsQ.data?.allowed_formats ?? [
      "image/jpeg",
      "image/png",
      "image/webp",
    ];
  const maxMb = settingsQ.data?.max_upload_mb ?? 20;

  const approvedVersion = versions.find(
    (v) => v.is_approved || v.status === "approved",
  );
  const assetById = new Map(assets.map((a) => [String(a.id), a]));
  const approvedAsset =
    approvedVersion?.asset_id != null
      ? (assetById.get(String(approvedVersion.asset_id)) ?? null)
      : null;
  const reorderCardPhotos = (fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex || saveCardPhotosMut.isPending) return;
    const next = leftPhotos.map((photo) => photo.url).filter(Boolean);
    const [moved] = next.splice(fromIndex, 1);
    if (!moved) return;
    next.splice(toIndex, 0, moved);
    saveCardPhotosMut.mutate(next);
  };

  useEffect(() => {
    if (
      !activeId ||
      !projectQ.data ||
      !projectNmId ||
      wbAssets.length > 0 ||
      autoImportAttemptedRef.current
    )
      return;
    autoImportAttemptedRef.current = true;
    importWbAssets(projectId, activeId)
      .then(() => {
        qc.invalidateQueries({ queryKey: projectKey });
        qc.invalidateQueries({ queryKey: ["photo", "projects", activeId] });
      })
      .catch(() => undefined);
  }, [
    activeId,
    projectId,
    projectKey,
    projectNmId,
    projectQ.data,
    qc,
    wbAssets.length,
  ]);

  if (!activeId) {
    return (
      <PageShell>
        <PageHeader title="Проект" />
        <NoAccountSelected />
      </PageShell>
    );
  }

  return (
    <div className="flex h-[100dvh] flex-col bg-background text-foreground">
      <div className="flex h-11 shrink-0 items-center border-b px-5">
        <Button
          asChild
          variant="ghost"
          size="sm"
          className="-ml-2 h-8 text-sm text-muted-foreground"
        >
          <Link to="/photo-studio">
            <ChevronLeft className="h-4 w-4 mr-1" /> Рабочее пространство
          </Link>
        </Button>
      </div>

      {projectQ.isLoading && (
        <div className="p-6">
          <Skeleton className="h-[70vh] w-full" />
        </div>
      )}
      {projectQ.error && (
        <div className="p-6">
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              {(projectQ.error as Error).message}
            </AlertDescription>
          </Alert>
        </div>
      )}

      {projectQ.data && (
        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[344px_minmax(0,1fr)_344px]">
          <aside className="flex min-h-0 flex-col border-r bg-background">
            <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
              <Button
                asChild
                variant="ghost"
                size="sm"
                className="-ml-2 h-8 text-sm"
              >
                <Link to="/photo-studio">
                  <ChevronLeft className="h-4 w-4 mr-1" /> Фото карточки
                </Link>
              </Button>
              <Button
                size="icon"
                variant="outline"
                className="h-8 w-8"
                disabled={importMut.isPending}
                onClick={() => importMut.mutate()}
              >
                <RefreshCcw
                  className={`h-4 w-4 ${importMut.isPending ? "animate-spin" : ""}`}
                />
              </Button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
              <div className="mb-4 px-1">
                <div className="line-clamp-2 text-sm font-semibold">
                  {photoProjectTitle(project, projectId)}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {project?.nm_id != null && (
                    <Badge
                      variant="outline"
                      className="bg-primary/5 text-[11px] text-primary"
                    >
                      Артикул: {project.nm_id}
                    </Badge>
                  )}
                  {project?.vendor_code && (
                    <Badge variant="outline" className="text-[11px]">
                      VendorCode: {project.vendor_code}
                    </Badge>
                  )}
                </div>
              </div>

              {leftPhotos.length === 0 ? (
                <div className="rounded-xl border border-dashed p-4 text-center text-xs text-muted-foreground">
                  <ImageOff className="mx-auto mb-2 h-7 w-7" />
                  Фото карточки не найдены.
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-3 h-8 w-full text-xs"
                    disabled={importMut.isPending}
                    onClick={() => importMut.mutate()}
                  >
                    <RefreshCcw className="h-3.5 w-3.5 mr-1" /> Импортировать
                  </Button>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {leftPhotos.map((photo) => (
                    <button
                      key={photo.key}
                      type="button"
                      draggable
                      className={`group relative aspect-[3/4] overflow-hidden rounded-xl border bg-muted text-left transition hover:ring-2 hover:ring-primary/40 ${
                        photo.asset && compare.left?.id === photo.asset.id
                          ? "ring-2 ring-primary"
                          : ""
                      } ${dragOverSlot === photo.index ? "ring-2 ring-primary" : ""}`}
                      onClick={() => {
                        if (photo.asset)
                          setCompare((c) => ({ ...c, left: photo.asset }));
                      }}
                      onDragStart={(event) => {
                        event.dataTransfer.setData(
                          "application/x-card-photo-index",
                          String(photo.index),
                        );
                        event.dataTransfer.setData(
                          "application/x-card-photo-url",
                          photo.url,
                        );
                        event.dataTransfer.effectAllowed = "move";
                      }}
                      onDragLeave={() =>
                        setDragOverSlot((slot) =>
                          slot === photo.index ? null : slot,
                        )
                      }
                      onDragOver={(event) => {
                        event.preventDefault();
                        const isCardPhoto = event.dataTransfer.types.includes(
                          "application/x-card-photo-index",
                        );
                        event.dataTransfer.dropEffect = isCardPhoto
                          ? "move"
                          : "copy";
                        setDragOverSlot(photo.index);
                      }}
                      onDrop={(event) => {
                        event.preventDefault();
                        setDragOverSlot(null);
                        const versionId =
                          event.dataTransfer.getData(
                            "application/x-photo-version-id",
                          ) || event.dataTransfer.getData("text/plain");
                        if (versionId) {
                          applyWbMut.mutate({
                            versionId,
                            photoNumber: photo.index + 1,
                          });
                          return;
                        }
                        const fromIndexRaw = event.dataTransfer.getData(
                          "application/x-card-photo-index",
                        );
                        if (fromIndexRaw) {
                          reorderCardPhotos(Number(fromIndexRaw), photo.index);
                        }
                      }}
                      onDragEnd={() => setDragOverSlot(null)}
                      disabled={
                        applyWbMut.isPending || saveCardPhotosMut.isPending
                      }
                    >
                      <SafePhotoImage
                        src={photo.url}
                        alt={`Фото ${photo.index + 1}`}
                        className="h-full w-full object-cover"
                      />
                      <span className="absolute right-1.5 top-1.5 grid h-6 w-6 place-items-center rounded bg-background/80 text-muted-foreground opacity-0 shadow transition group-hover:opacity-100">
                        <GripVertical className="h-3.5 w-3.5" />
                      </span>
                      {photo.index === 0 && (
                        <Badge className="absolute left-2 top-2 bg-destructive text-[10px] text-destructive-foreground">
                          ОБЛОЖКА
                        </Badge>
                      )}
                      {!photo.asset && (
                        <Badge
                          variant="outline"
                          className="absolute left-2 bottom-1.5 bg-background/85 text-[10px]"
                        >
                          WB
                        </Badge>
                      )}
                      <span className="absolute bottom-1.5 right-1.5 rounded bg-background/80 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {photo.index + 1}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              <div className="mt-3">
                <UploadZone
                  projectId={projectId}
                  accountId={activeId}
                  allowedFormats={allowedFormats}
                  maxMb={maxMb}
                  onUploaded={() =>
                    qc.invalidateQueries({ queryKey: projectKey })
                  }
                />
              </div>

              {assets.length === 0 && (
                <div className="mt-3 rounded-xl border border-dashed p-3 text-[11px] text-muted-foreground">
                  Чтобы прикрепить изображение к чату, сначала импортируйте или
                  загрузите фото.
                </div>
              )}
            </div>
          </aside>

          <main className="min-h-0 border-r bg-background">
            <PhotoChatPanel
              projectId={projectId}
              accountId={activeId}
              assets={assets}
              jobs={jobs}
              comments={comments}
              generationOk={generationOk}
              supportedOps={supportedOps}
              onChanged={() => qc.invalidateQueries({ queryKey: projectKey })}
            />
          </main>

          <aside className="flex min-h-0 flex-col bg-background">
            <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Sparkles className="h-4 w-4 text-primary" /> История
              </div>
              <Badge variant="outline" className="text-[11px]">
                {versions.length} / {jobs.length}
              </Badge>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
              <div className="mb-3 text-xs text-muted-foreground">
                Перетащите результат в карточку товара или выберите версию для
                проверки.
              </div>

              {versions.length === 0 ? (
                <div className="rounded-xl border border-dashed p-5 text-center text-xs text-muted-foreground">
                  <Sparkles className="mx-auto mb-2 h-7 w-7" />
                  Готовые варианты появятся здесь после обработки.
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-2">
                  {versions.map((v) => {
                    const img =
                      v.thumbnail ??
                      v.url ??
                      assetById.get(String(v.asset_id ?? ""))?.thumbnail ??
                      null;
                    return (
                      <button
                        key={String(v.id)}
                        type="button"
                        draggable
                        className="group relative aspect-[3/4] overflow-hidden rounded-xl border bg-muted transition hover:ring-2 hover:ring-primary/40"
                        onDragStart={(event) => {
                          event.dataTransfer.setData(
                            "application/x-photo-version-id",
                            String(v.id),
                          );
                          event.dataTransfer.setData(
                            "text/plain",
                            String(v.id),
                          );
                          event.dataTransfer.effectAllowed = "copy";
                        }}
                        onClick={() => {
                          setCompare((c) => ({
                            left:
                              assetById.get(String(v.asset_id ?? "")) ??
                              c.left ??
                              wbAssets[0] ??
                              userAssets[0] ??
                              null,
                            right: v,
                          }));
                        }}
                      >
                        {img ? (
                          <SafePhotoImage
                            src={img}
                            alt={`Версия ${v.number ?? v.version_number ?? v.id}`}
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <div className="flex h-full items-center justify-center text-muted-foreground">
                            <ImageOff className="h-5 w-5" />
                          </div>
                        )}
                        {(v.is_approved || v.status === "approved") && (
                          <Badge className="absolute left-1.5 top-1.5 bg-success text-[10px] text-success-foreground">
                            OK
                          </Badge>
                        )}
                        <span
                          className="absolute bottom-1.5 left-1.5 rounded-md bg-primary px-2 py-1 text-[10px] font-semibold text-primary-foreground opacity-0 shadow transition group-hover:opacity-100"
                          onClick={(event) => {
                            event.stopPropagation();
                            applyWbMut.mutate({
                              versionId: v.id,
                              photoNumber: 1,
                            });
                          }}
                        >
                          WB
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}

              {jobs.length > 0 && (
                <div className="mt-4">
                  <JobsBlock
                    jobs={jobs}
                    accountId={activeId}
                    refetchInterval={() =>
                      qc.invalidateQueries({ queryKey: projectKey })
                    }
                  />
                </div>
              )}

              {compare.right && (
                <Card className="mt-4">
                  <CardContent className="p-3 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold">Сравнение</div>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs"
                        onClick={() =>
                          setCompare({ left: compare.left, right: null })
                        }
                      >
                        Закрыть
                      </Button>
                    </div>
                    <CompareView left={compare.left} right={compare.right} />
                  </CardContent>
                </Card>
              )}

              {approvedVersion && (
                <Card className="mt-4">
                  <CardContent className="p-3 space-y-2">
                    <div className="text-xs uppercase text-muted-foreground">
                      Одобренная версия
                    </div>
                    <Button
                      size="sm"
                      className="w-full"
                      disabled={approvedVersion.asset_id == null}
                      onClick={async () => {
                        if (approvedVersion.asset_id == null) return;
                        try {
                          const r = await fetchPhotoAssetDownloadUrl(
                            approvedVersion.asset_id,
                            activeId,
                          );
                          if (r.url)
                            window.open(r.url, "_blank", "noopener,noreferrer");
                        } catch (e: any) {
                          toast.error(
                            e?.message ?? "Не удалось подготовить ссылку",
                          );
                        }
                      }}
                    >
                      <Download className="h-3.5 w-3.5 mr-1" /> Скачать
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full"
                      onClick={() => setManualOpen(true)}
                    >
                      <Send className="h-3.5 w-3.5 mr-1" /> Обновлено в WB
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full"
                      onClick={() => experimentMut.mutate()}
                      disabled={experimentMut.isPending}
                    >
                      <Sparkles className="h-3.5 w-3.5 mr-1" />{" "}
                      {PHOTO_STUDIO_EXPERIMENT_LABEL}
                    </Button>
                  </CardContent>
                </Card>
              )}

              {generation !== "ok" && (
                <Alert className="mt-4">
                  <Info className="h-4 w-4" />
                  <AlertTitle>ИИ-обработка не подключена</AlertTitle>
                  <AlertDescription>
                    Можно загружать готовые фото и вести историю проекта.
                  </AlertDescription>
                </Alert>
              )}
            </div>
          </aside>
        </div>
      )}

      <Dialog open={manualOpen} onOpenChange={setManualOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Зафиксировать ручное обновление в WB</DialogTitle>
            <DialogDescription>
              Эта запись не отправляет ничего в Wildberries — она только
              помогает связать ваше действие с будущими метриками.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <div>
              <div className="text-[11px] uppercase text-muted-foreground mb-1">
                Дата обновления
              </div>
              <Input
                type="date"
                value={manualDate}
                onChange={(e) => setManualDate(e.target.value)}
              />
            </div>
            <div>
              <div className="text-[11px] uppercase text-muted-foreground mb-1">
                Комментарий (необязательно)
              </div>
              <Textarea
                value={manualComment}
                onChange={(e) => setManualComment(e.target.value)}
                rows={2}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setManualOpen(false)}>
              Отмена
            </Button>
            <Button
              onClick={() => manualMut.mutate()}
              disabled={manualMut.isPending || !manualDate}
            >
              Подтвердить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
