// @ts-nocheck
// «Поставка по регионам / Отгрузка из наличия».
//
// Flow:
//   1. Шаблон / наличие  — скачать template или загрузить файл / draft
//   2. Превью наличия    — POST /portal/stock-control/preview (kind=regional_supply)
//   3. Параметры         — demand run, режим (redistribute/balance), доп. настройки
//   4. Запуск            — POST /portal/stock-control/runs (+ polling)
//   5. План по регионам  — GET /runs/:id, /runs/:id/rows, export
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { api, ApiError, getBaseUrl, getAccessToken } from "@/lib/api";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Download, FileUp, AlertTriangle, CheckCircle2, Loader2,
  Play, ChevronLeft, ChevronRight, RotateCcw, MapPin,
} from "lucide-react";
import { formatNumber, formatDateTime } from "@/lib/format";

type SupplyMode = "redistribute" | "balance";

interface Settings {
  uploadId: number | string | null;       // загруженный файл наличия
  useDraft: boolean;                       // использовать сохранённый draft
  demandRunId: number | string | null;     // источник спроса (return run)
  mode: SupplyMode;
  shipAllAvailable: boolean;
  defaultIl: boolean;                      // отгрузка в default ИЛ при отсутствии спроса
  minHistoryOrders: number;
  maxShareRatio: number;                   // 0..1
  excludedRegions: string[];
}

interface PreviewResp {
  data_freshness?: { stock_snapshot_at?: string | null; [k: string]: any } | null;
  rows_count?: number | null;
  products_count?: number | null;
  warehouses_count?: number | null;
  unmatched_rows?: number | null;
  warnings?: string[];
  errors?: string[];
  ready_to_run?: boolean;
  [k: string]: any;
}

interface RunResp {
  id?: number | string;
  status?: string;
  progress?: number | null;
  message?: string | null;
  summary?: {
    planned_units?: number | null;
    demand_units?: number | null;
    extra_units?: number | null;
    uncovered_units?: number | null;
    regions_count?: number | null;
    [k: string]: any;
  } | null;
  [k: string]: any;
}

const HUMAN: Record<string, string> = {
  warehouse_mapping_incomplete: "Не все склады сопоставлены с регионами.",
  no_demand_run:                "Не указан расчёт спроса (demand run).",
  draft_empty:                  "Черновик наличия пуст.",
  upload_unmatched_rows:        "Часть строк не сопоставилась — проверьте артикулы.",
};
const humanize = (s: string) => HUMAN[s] ?? s;

export function RegionalSupplyWizard({ accountId }: { accountId: number }) {
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1);
  const [settings, setSettings] = useState<Settings>({
    uploadId: null,
    useDraft: false,
    demandRunId: null,
    mode: "redistribute",
    shipAllAvailable: false,
    defaultIl: true,
    minHistoryOrders: 5,
    maxShareRatio: 0.5,
    excludedRegions: [],
  });
  const [preview, setPreview] = useState<PreviewResp | null>(null);
  const [runId, setRunId] = useState<number | string | null>(null);

  const patch = (p: Partial<Settings>) => setSettings((s) => ({ ...s, ...p }));
  const restart = () => { setStep(1); setRunId(null); setPreview(null); };

  return (
    <Card>
      <CardContent className="p-4 md:p-6 space-y-6">
        <StepBar step={step} />

        {step === 1 && (
          <Step1Upload
            accountId={accountId}
            settings={settings}
            onChange={patch}
            onNext={() => setStep(2)}
          />
        )}
        {step === 2 && (
          <Step2Preview
            accountId={accountId}
            settings={settings}
            preview={preview}
            setPreview={setPreview}
            onBack={() => setStep(1)}
            onNext={() => setStep(3)}
          />
        )}
        {step === 3 && (
          <Step3Params
            accountId={accountId}
            settings={settings}
            onChange={patch}
            onBack={() => setStep(2)}
            onNext={() => setStep(4)}
          />
        )}
        {step === 4 && (
          <Step4Run
            accountId={accountId}
            settings={settings}
            runId={runId}
            setRunId={setRunId}
            onBack={() => setStep(3)}
            onDone={() => setStep(5)}
          />
        )}
        {step === 5 && runId != null && (
          <Step5Plan accountId={accountId} runId={runId} onRestart={restart} />
        )}
      </CardContent>
    </Card>
  );
}

// ─── Step bar ────────────────────────────────────────────────────────
function StepBar({ step }: { step: 1 | 2 | 3 | 4 | 5 }) {
  const labels = ["Наличие", "Превью", "Параметры", "Запуск", "План"];
  return (
    <div className="flex items-center gap-2 overflow-x-auto">
      {labels.map((l, i) => {
        const n = (i + 1) as 1 | 2 | 3 | 4 | 5;
        const active = n === step;
        const done = n < step;
        return (
          <div key={l} className="flex items-center gap-2 shrink-0">
            <div
              className={[
                "h-7 w-7 rounded-full flex items-center justify-center text-xs font-semibold border",
                active && "bg-primary text-primary-foreground border-primary",
                done && "bg-success/15 text-success border-success/30",
                !active && !done && "bg-muted text-muted-foreground border-border",
              ].filter(Boolean).join(" ")}
            >
              {done ? <CheckCircle2 className="h-4 w-4" /> : n}
            </div>
            <span className={["text-xs whitespace-nowrap", active ? "font-semibold text-foreground" : "text-muted-foreground"].join(" ")}>
              {l}
            </span>
            {i < labels.length - 1 && <ChevronRight className="h-3 w-3 text-muted-foreground" />}
          </div>
        );
      })}
    </div>
  );
}

// ─── Step 1: Upload / draft / template ───────────────────────────────
function Step1Upload({
  accountId, settings, onChange, onNext,
}: {
  accountId: number;
  settings: Settings;
  onChange: (p: Partial<Settings>) => void;
  onNext: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const handleFile = async (f: File) => {
    setUploading(true); setErr(null);
    try {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("account_id", String(accountId));
      fd.append("kind", "store_balance");
      const res = await api<{ upload_id?: number | string; id?: number | string }>(
        API_ENDPOINTS.portal.stockControlUpload,
        { method: "POST", formData: fd },
      );
      const id = (res as any)?.upload_id ?? (res as any)?.id ?? null;
      if (id == null) throw new Error("Сервер не вернул upload_id");
      onChange({ uploadId: id, useDraft: false });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const downloadTemplate = () => {
    const base = getBaseUrl();
    const token = getAccessToken();
    const url = `${base}${API_ENDPOINTS.portal.stockControlTemplate}?account_id=${accountId}&kind=store_balance${
      token ? `&access_token=${encodeURIComponent(token)}` : ""
    }`;
    window.open(url, "_blank", "noopener");
  };

  const canNext = settings.uploadId != null || settings.useDraft;

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold">Шаг 1. Наличие товара</h3>
        <p className="text-sm text-muted-foreground">
          Скачайте шаблон, заполните количеством по складам и загрузите — или используйте сохранённый черновик.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={downloadTemplate} className="gap-2">
          <Download className="h-4 w-4" /> Скачать шаблон наличия
        </Button>
      </div>

      <div className="rounded-md border p-3 space-y-2">
        <Label className="text-sm flex items-center gap-2">
          <FileUp className="h-4 w-4" /> Загрузить файл наличия (.xlsx)
        </Label>
        <Input
          type="file"
          accept=".xlsx,.xls"
          disabled={uploading}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleFile(f);
          }}
        />
        {uploading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Загрузка…
          </div>
        )}
        {settings.uploadId != null && !uploading && (
          <div className="flex items-center gap-2 text-xs text-success">
            <CheckCircle2 className="h-3 w-3" />
            Файл загружен (upload #{settings.uploadId})
          </div>
        )}
        {err && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{err}</AlertDescription>
          </Alert>
        )}
      </div>

      <div className="flex items-center justify-between rounded-md border p-3">
        <div>
          <Label className="text-sm">Использовать сохранённый черновик</Label>
          <p className="text-xs text-muted-foreground">
            Берёт последний draft наличия с этого аккаунта.
          </p>
        </div>
        <Switch
          checked={settings.useDraft}
          onCheckedChange={(v) => onChange({ useDraft: v, ...(v ? { uploadId: null } : {}) })}
        />
      </div>

      <NavButtons canNext={canNext} onNext={onNext} />
    </div>
  );
}

// ─── Step 2: Preview наличия ─────────────────────────────────────────
function buildPreviewBody(accountId: number, s: Settings) {
  return {
    account_id: accountId,
    mode: "regional_supply",
    upload_id: s.uploadId ?? null,
    use_draft: s.useDraft,
  };
}

function Step2Preview({
  accountId, settings, preview, setPreview, onBack, onNext,
}: {
  accountId: number;
  settings: Settings;
  preview: PreviewResp | null;
  setPreview: (p: PreviewResp | null) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const m = useMutation({
    mutationFn: () =>
      api<PreviewResp>(API_ENDPOINTS.portal.stockControlPreview, {
        method: "POST",
        body: buildPreviewBody(accountId, settings),
      }),
    onSuccess: (d) => setPreview(d),
  });

  useEffect(() => {
    if (!preview && !m.isPending && !m.isError) m.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hasErrors = (preview?.errors?.length ?? 0) > 0;
  const ready = preview?.ready_to_run !== false && !hasErrors;

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">Шаг 2. Превью наличия</h3>
          <p className="text-sm text-muted-foreground">
            Проверка строк, артикулов и сопоставления со складами.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => m.mutate()} disabled={m.isPending}>
          <RotateCcw className="h-3 w-3 mr-1" /> Обновить
        </Button>
      </div>

      {m.isPending && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)}
        </div>
      )}

      {m.isError && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Не удалось получить превью</AlertTitle>
          <AlertDescription>{(m.error as Error).message}</AlertDescription>
        </Alert>
      )}

      {preview && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MiniStat label="Строк наличия" value={preview.rows_count} />
            <MiniStat label="Товары" value={preview.products_count} />
            <MiniStat label="Склады" value={preview.warehouses_count} />
            <MiniStat
              label="Несопоставленные"
              value={preview.unmatched_rows}
              tone={preview.unmatched_rows ? "warning" : "default"}
            />
          </div>

          {preview.data_freshness?.stock_snapshot_at && (
            <Card className="bg-muted/30">
              <CardContent className="p-3 text-xs">
                Снимок остатков:{" "}
                <span className="tabular-nums">
                  {formatDateTime(preview.data_freshness.stock_snapshot_at)}
                </span>
              </CardContent>
            </Card>
          )}

          {Array.isArray(preview.warnings) && preview.warnings.length > 0 && (
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Предупреждения</AlertTitle>
              <AlertDescription>
                <ul className="list-disc pl-5 text-sm space-y-0.5">
                  {preview.warnings.map((w, i) => <li key={i}>{humanize(w)}</li>)}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {hasErrors && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Ошибки</AlertTitle>
              <AlertDescription>
                <ul className="list-disc pl-5 text-sm space-y-0.5">
                  {preview.errors!.map((w, i) => <li key={i}>{humanize(w)}</li>)}
                </ul>
              </AlertDescription>
            </Alert>
          )}
        </>
      )}

      <NavButtons onBack={onBack} canNext={!!preview && ready} onNext={onNext} />
    </div>
  );
}

// ─── Step 3: Params (demand run + mode + extras) ─────────────────────
function Step3Params({
  accountId, settings, onChange, onBack, onNext,
}: {
  accountId: number;
  settings: Settings;
  onChange: (p: Partial<Settings>) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const runs = useQuery<{ items?: any[] } | any[]>({
    queryKey: ["stock-control-runs", accountId, "for-supply"],
    queryFn: () =>
      api(API_ENDPOINTS.portal.stockControlRuns, {
        query: { account_id: accountId, kind: "return_excess", status: "success", limit: 25 },
      }),
    staleTime: 60_000,
  });

  const runItems = useMemo(() => {
    const r: any = runs.data;
    if (!r) return [];
    if (Array.isArray(r)) return r;
    return Array.isArray(r.items) ? r.items : [];
  }, [runs.data]);

  const [regionInput, setRegionInput] = useState("");
  const addRegion = () => {
    const t = regionInput.trim();
    if (!t || settings.excludedRegions.includes(t)) { setRegionInput(""); return; }
    onChange({ excludedRegions: [...settings.excludedRegions, t] });
    setRegionInput("");
  };

  const canNext = settings.demandRunId != null || settings.shipAllAvailable;

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold">Шаг 3. Параметры распределения</h3>
        <p className="text-sm text-muted-foreground">
          Выберите расчёт спроса и режим распределения.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label>Расчёт спроса (demand run)</Label>
        <Select
          value={settings.demandRunId != null ? String(settings.demandRunId) : ""}
          onValueChange={(v) => onChange({ demandRunId: v || null })}
          disabled={runs.isLoading}
        >
          <SelectTrigger>
            <SelectValue placeholder={runs.isLoading ? "Загрузка…" : "Выберите расчёт"} />
          </SelectTrigger>
          <SelectContent>
            {runItems.map((r: any) => (
              <SelectItem key={r.id} value={String(r.id)}>
                #{r.id} · {r.created_at ? formatDateTime(r.created_at) : "—"}
                {r.summary?.shortage_units != null ? ` · дефицит ${formatNumber(r.summary.shortage_units)}` : ""}
              </SelectItem>
            ))}
            {runItems.length === 0 && !runs.isLoading && (
              <div className="px-2 py-1.5 text-xs text-muted-foreground">Нет успешных расчётов</div>
            )}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Источник дефицита по регионам. Без него — только отгрузка всего наличия.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label>Режим</Label>
        <Select value={settings.mode} onValueChange={(v) => onChange({ mode: v as SupplyMode })}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="redistribute">Redistribute — перераспределить по спросу</SelectItem>
            <SelectItem value="balance">Balance — выровнять остатки</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Separator />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="flex items-center justify-between rounded-md border p-3">
          <div>
            <Label className="text-sm">Отгрузить всё наличие</Label>
            <p className="text-xs text-muted-foreground">Даже сверх рассчитанного спроса.</p>
          </div>
          <Switch
            checked={settings.shipAllAvailable}
            onCheckedChange={(v) => onChange({ shipAllAvailable: v })}
          />
        </div>
        <div className="flex items-center justify-between rounded-md border p-3">
          <div>
            <Label className="text-sm">Default ИЛ при отсутствии спроса</Label>
            <p className="text-xs text-muted-foreground">Отгрузка в опорный ИЛ.</p>
          </div>
          <Switch
            checked={settings.defaultIl}
            onCheckedChange={(v) => onChange({ defaultIl: v })}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="rs-min-hist">Минимум заказов в истории</Label>
          <Input id="rs-min-hist" type="number" min={0} step={1}
            value={settings.minHistoryOrders}
            onChange={(e) => onChange({ minHistoryOrders: Math.max(0, Number(e.target.value) || 0) })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rs-max-share">Max доля региона (0–1)</Label>
          <Input id="rs-max-share" type="number" min={0} max={1} step={0.05}
            value={settings.maxShareRatio}
            onChange={(e) => onChange({ maxShareRatio: Math.min(1, Math.max(0, Number(e.target.value) || 0)) })}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>Исключённые регионы</Label>
        <div className="flex gap-2">
          <Input
            placeholder="Например: Калининград"
            value={regionInput}
            onChange={(e) => setRegionInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addRegion(); }}}
          />
          <Button type="button" variant="outline" onClick={addRegion}>Добавить</Button>
        </div>
        {settings.excludedRegions.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {settings.excludedRegions.map((r) => (
              <Badge key={r} variant="secondary" className="gap-1 cursor-pointer"
                onClick={() => onChange({ excludedRegions: settings.excludedRegions.filter((x) => x !== r) })}>
                {r} ×
              </Badge>
            ))}
          </div>
        )}
      </div>

      <NavButtons onBack={onBack} canNext={canNext} onNext={onNext} />
    </div>
  );
}

// ─── Step 4: Run ─────────────────────────────────────────────────────
function buildRunBody(accountId: number, s: Settings) {
  return {
    account_id: accountId,
    kind: "regional_supply",
    upload_id: s.uploadId,
    use_draft: s.useDraft,
    demand_run_id: s.demandRunId,
    mode: s.mode,
    ship_all_available: s.shipAllAvailable,
    default_il: s.defaultIl,
    min_history_orders: s.minHistoryOrders,
    max_share_ratio: s.maxShareRatio,
    excluded_regions: s.excludedRegions,
  };
}

function Step4Run({
  accountId, settings, runId, setRunId, onBack, onDone,
}: {
  accountId: number;
  settings: Settings;
  runId: number | string | null;
  setRunId: (id: number | string | null) => void;
  onBack: () => void;
  onDone: () => void;
}) {
  const start = useMutation({
    mutationFn: () =>
      api<RunResp>(API_ENDPOINTS.portal.stockControlRuns, {
        method: "POST",
        body: buildRunBody(accountId, settings),
      }),
    onSuccess: (d) => {
      const id = (d as any)?.id ?? null;
      if (id != null) setRunId(id);
    },
  });

  const poll = useQuery({
    queryKey: ["stock-control-run", runId, "supply"],
    queryFn: () =>
      api<RunResp>(API_ENDPOINTS.portal.stockControlRunDetail(runId!), {
        query: { account_id: accountId },
      }),
    enabled: runId != null,
    refetchInterval: (q) => {
      const s = (q.state.data as RunResp | undefined)?.status;
      return s === "success" || s === "failed" ? false : 2000;
    },
  });

  const status = poll.data?.status ?? (runId ? "queued" : null);
  const raw = poll.data?.progress ?? null;
  const pct = raw == null ? null : raw <= 1 ? Math.round(raw * 100) : Math.round(raw);

  useEffect(() => { if (status === "success") onDone(); }, [status, onDone]);

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold">Шаг 4. Запуск распределения</h3>
        <p className="text-sm text-muted-foreground">Расчёт выполняется на сервере.</p>
      </div>

      {runId == null && (
        <div className="space-y-3">
          {start.isError && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Не удалось запустить расчёт</AlertTitle>
              <AlertDescription>{(start.error as Error).message}</AlertDescription>
            </Alert>
          )}
          <Button onClick={() => start.mutate()} disabled={start.isPending} className="gap-2">
            {start.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Запустить
          </Button>
        </div>
      )}

      {runId != null && (
        <Card>
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-sm">Расчёт <span className="font-mono">#{runId}</span></div>
              <RunStatusBadge status={status} />
            </div>
            <Progress value={pct ?? (status === "success" ? 100 : 5)} />
            {poll.data?.message && (
              <div className="text-xs text-muted-foreground">{poll.data.message}</div>
            )}
            {status === "failed" && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Расчёт завершился с ошибкой</AlertTitle>
                <AlertDescription>{poll.data?.message ?? "Неизвестная ошибка"}</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      )}

      <div className="flex justify-between">
        <Button variant="outline" onClick={onBack} disabled={start.isPending}>
          <ChevronLeft className="h-4 w-4 mr-1" /> Назад
        </Button>
        {status === "success" && (
          <Button onClick={onDone}>К плану <ChevronRight className="h-4 w-4 ml-1" /></Button>
        )}
      </div>
    </div>
  );
}

function RunStatusBadge({ status }: { status: string | null }) {
  const map: Record<string, { label: string; cls: string }> = {
    queued:  { label: "В очереди",   cls: "bg-muted text-muted-foreground border-border" },
    running: { label: "Выполняется", cls: "bg-primary/10 text-primary border-primary/30" },
    success: { label: "Готово",      cls: "bg-success/10 text-success border-success/30" },
    failed:  { label: "Ошибка",      cls: "bg-destructive/10 text-destructive border-destructive/30" },
  };
  const meta = (status && map[status]) || map.queued;
  return <Badge variant="outline" className={meta.cls}>{meta.label}</Badge>;
}

// ─── Step 5: Plan ────────────────────────────────────────────────────
function badgeFor(source?: string | null): { label: string; cls: string } | null {
  if (!source) return null;
  switch (source) {
    case "history":           return { label: "История товара",              cls: "bg-primary/10 text-primary border-primary/30" };
    case "default_il":        return { label: "Default ИЛ",                  cls: "bg-muted text-muted-foreground border-border" };
    case "default_il_no_demand":  return { label: "Default ИЛ: нет спроса",  cls: "bg-muted text-muted-foreground border-border" };
    case "default_il_low_history":return { label: "Default ИЛ: мало истории",cls: "bg-warning/10 text-warning border-warning/30" };
    case "default_il_anomaly":    return { label: "Default ИЛ: аномалия",    cls: "bg-warning/10 text-warning border-warning/30" };
    default: return { label: source, cls: "bg-muted text-muted-foreground border-border" };
  }
}

function Step5Plan({
  accountId, runId, onRestart,
}: {
  accountId: number;
  runId: number | string;
  onRestart: () => void;
}) {
  const detail = useQuery({
    queryKey: ["stock-control-run", runId, "supply-detail"],
    queryFn: () =>
      api<RunResp>(API_ENDPOINTS.portal.stockControlRunDetail(runId), {
        query: { account_id: accountId },
      }),
    staleTime: 60_000,
  });

  const rows = useQuery<{ items?: any[] } | any[]>({
    queryKey: ["stock-control-run", runId, "supply-rows"],
    queryFn: () =>
      api(API_ENDPOINTS.portal.stockControlRunRows(runId), {
        query: { account_id: accountId, limit: 100 },
      }),
    staleTime: 60_000,
  });

  const items = useMemo(() => {
    const r: any = rows.data;
    if (!r) return [];
    if (Array.isArray(r)) return r;
    return Array.isArray(r.items) ? r.items : [];
  }, [rows.data]);

  const summary = detail.data?.summary ?? null;

  const exportUrl = (() => {
    const base = getBaseUrl();
    const token = getAccessToken();
    return `${base}${API_ENDPOINTS.portal.stockControlRunExport(runId)}?account_id=${accountId}${
      token ? `&access_token=${encodeURIComponent(token)}` : ""
    }`;
  })();

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold flex items-center gap-2">
            <MapPin className="h-4 w-4" /> План по регионам · #{runId}
          </h3>
          <p className="text-sm text-muted-foreground">
            Рекомендация по отгрузке. Изменения в WB автоматически не применяются.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={exportUrl} target="_blank" rel="noopener noreferrer">
              <Download className="h-3 w-3 mr-1" /> Excel
            </a>
          </Button>
          <Button variant="ghost" size="sm" onClick={onRestart}>
            <RotateCcw className="h-3 w-3 mr-1" /> Новый расчёт
          </Button>
        </div>
      </div>

      {detail.isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20" />)}
        </div>
      ) : summary ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <MiniStat label="Запланировано" value={summary.planned_units} />
          <MiniStat label="По спросу" value={summary.demand_units} />
          <MiniStat label="Доп. отгрузка" value={summary.extra_units} />
          <MiniStat label="Не закрыто" value={summary.uncovered_units} tone="warning" />
          <MiniStat label="Регионов" value={summary.regions_count} />
        </div>
      ) : null}

      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold">План отгрузки (первые 100)</div>
            <div className="text-xs text-muted-foreground">
              {rows.isLoading ? "Загрузка…" : `Показано: ${items.length}`}
            </div>
          </div>

          {rows.isLoading && (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-8" />)}
            </div>
          )}

          {!rows.isLoading && items.length === 0 && (
            <div className="text-sm text-muted-foreground py-4 text-center">
              Расчёт не выявил позиций для отгрузки.
            </div>
          )}

          {!rows.isLoading && items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs uppercase text-muted-foreground border-b">
                    <th className="text-left py-1.5 pr-3">Регион</th>
                    <th className="text-left py-1.5 pr-3">Склад</th>
                    <th className="text-left py-1.5 pr-3">Товар</th>
                    <th className="text-left py-1.5 pr-3">Размер</th>
                    <th className="text-right py-1.5 pr-3">Дефицит</th>
                    <th className="text-right py-1.5 pr-3">План</th>
                    <th className="text-right py-1.5 pr-3">По спросу</th>
                    <th className="text-right py-1.5 pr-3">Доп.</th>
                    <th className="text-left py-1.5">Источник</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((r: any, i: number) => {
                    const b = badgeFor(r.allocation_source ?? r.source);
                    return (
                      <tr key={r.id ?? i} className="border-b last:border-0">
                        <td className="py-1.5 pr-3">{r.region ?? "—"}</td>
                        <td className="py-1.5 pr-3">{r.warehouse ?? r.warehouse_name ?? "—"}</td>
                        <td className="py-1.5 pr-3">
                          {r.nm_id ? (
                            <Link
                              to="/products/$nmId"
                              params={{ nmId: String(r.nm_id) }}
                              className="text-primary hover:underline"
                            >
                              {r.vendor_code || r.nm_id}
                            </Link>
                          ) : (r.vendor_code ?? "—")}
                        </td>
                        <td className="py-1.5 pr-3">{r.size ?? r.tech_size ?? "—"}</td>
                        <td className="py-1.5 pr-3 text-right tabular-nums">
                          {r.open_shortage_units != null ? formatNumber(r.open_shortage_units) : "—"}
                        </td>
                        <td className="py-1.5 pr-3 text-right tabular-nums font-semibold">
                          {r.planned_units != null ? formatNumber(r.planned_units) : "—"}
                        </td>
                        <td className="py-1.5 pr-3 text-right tabular-nums">
                          {r.demand_units != null ? formatNumber(r.demand_units) : "—"}
                        </td>
                        <td className="py-1.5 pr-3 text-right tabular-nums">
                          {r.extra_units != null ? formatNumber(r.extra_units) : "—"}
                        </td>
                        <td className="py-1.5">
                          {b ? <Badge variant="outline" className={b.cls}>{b.label}</Badge> : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Shared ──────────────────────────────────────────────────────────
function MiniStat({
  label, value, tone = "default",
}: { label: string; value?: number | null; tone?: "default" | "warning" }) {
  const cls = tone === "warning" ? "border-warning/30" : "border-border";
  return (
    <Card className={cls}>
      <CardContent className="p-3 space-y-1">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="text-xl font-semibold tabular-nums">
          {value != null ? formatNumber(value) : "—"}
        </div>
      </CardContent>
    </Card>
  );
}

function NavButtons({
  onBack, onNext, canNext = true, nextLabel = "Далее",
}: {
  onBack?: () => void;
  onNext: () => void;
  canNext?: boolean;
  nextLabel?: string;
}) {
  return (
    <div className="flex justify-between pt-2">
      {onBack ? (
        <Button variant="outline" onClick={onBack}>
          <ChevronLeft className="h-4 w-4 mr-1" /> Назад
        </Button>
      ) : <span />}
      <Button onClick={onNext} disabled={!canNext}>
        {nextLabel} <ChevronRight className="h-4 w-4 ml-1" />
      </Button>
    </div>
  );
}
