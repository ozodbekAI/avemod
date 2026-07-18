// @ts-nocheck
// «Баланс магазинов» — перераспределение остатков между двумя аккаунтами WB.
//
// Flow:
//   1. Аккаунты      — выбрать донор и получатель (требуется доступ к обоим)
//   2. Превью        — POST /portal/stock-control/preview (kind=store_balance)
//   3. Параметры     — режим, пороги, минимальные остатки
//   4. Запуск        — POST /portal/stock-control/runs (+ polling)
//   5. План          — GET /runs/:id, /runs/:id/rows, export
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { api, ApiError, getBaseUrl, getAccessToken } from "@/lib/api";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { useAccounts } from "@/lib/account-context";
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
  AlertTriangle, CheckCircle2, Loader2, Play, ChevronLeft, ChevronRight,
  RotateCcw, Download, ArrowRightLeft, Store,
} from "lucide-react";
import { formatNumber, formatDateTime } from "@/lib/format";

type BalanceMode = "donor_recipient" | "equalize";

interface Settings {
  sourceAccountId: number | null;
  targetAccountId: number | null;
  mode: BalanceMode;
  minSourceStock: number;      // не отгружать ниже этого уровня в доноре
  maxTargetStock: number;      // не загружать выше этого уровня в получателе
  sizeAware: boolean;
  excludedNmIds: string[];
}

interface PreviewResp {
  data_freshness?: { stock_snapshot_at?: string | null; [k: string]: any } | null;
  source_skus_count?: number | null;
  target_skus_count?: number | null;
  shared_skus_count?: number | null;
  source_excess_units?: number | null;
  target_shortage_units?: number | null;
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
    skus_count?: number | null;
    source_excess_units?: number | null;
    target_shortage_units?: number | null;
    uncovered_units?: number | null;
    [k: string]: any;
  } | null;
  [k: string]: any;
}

const HUMAN: Record<string, string> = {
  same_account:                  "Донор и получатель не могут быть одним аккаунтом.",
  no_shared_skus:                "У аккаунтов нет общих SKU — балансировать нечего.",
  source_stock_stale:            "Снимок остатков донора устарел.",
  target_stock_stale:            "Снимок остатков получателя устарел.",
  warehouse_mapping_incomplete:  "Не все склады сопоставлены — план может быть неполным.",
};
const humanize = (s: string) => HUMAN[s] ?? s;

export function StoreBalanceWizard({ accountId }: { accountId: number }) {
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1);
  const [settings, setSettings] = useState<Settings>({
    sourceAccountId: accountId,
    targetAccountId: null,
    mode: "donor_recipient",
    minSourceStock: 0,
    maxTargetStock: 0,
    sizeAware: true,
    excludedNmIds: [],
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
          <Step1Accounts
            settings={settings}
            onChange={patch}
            onNext={() => setStep(2)}
          />
        )}
        {step === 2 && (
          <Step2Preview
            settings={settings}
            preview={preview}
            setPreview={setPreview}
            onBack={() => setStep(1)}
            onNext={() => setStep(3)}
          />
        )}
        {step === 3 && (
          <Step3Params
            settings={settings}
            onChange={patch}
            onBack={() => setStep(2)}
            onNext={() => setStep(4)}
          />
        )}
        {step === 4 && (
          <Step4Run
            settings={settings}
            runId={runId}
            setRunId={setRunId}
            onBack={() => setStep(3)}
            onDone={() => setStep(5)}
          />
        )}
        {step === 5 && runId != null && (
          <Step5Plan
            sourceAccountId={settings.sourceAccountId!}
            runId={runId}
            onRestart={restart}
          />
        )}
      </CardContent>
    </Card>
  );
}

// ─── Step bar ────────────────────────────────────────────────────────
function StepBar({ step }: { step: 1 | 2 | 3 | 4 | 5 }) {
  const labels = ["Аккаунты", "Превью", "Параметры", "Запуск", "План"];
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

// ─── Step 1: Accounts ────────────────────────────────────────────────
function Step1Accounts({
  settings, onChange, onNext,
}: {
  settings: Settings;
  onChange: (p: Partial<Settings>) => void;
  onNext: () => void;
}) {
  const { accounts, loading } = useAccounts();

  const accountName = (id: number | null) =>
    accounts.find((a) => a.id === id)?.name ?? `#${id}`;

  const sameAccount =
    settings.sourceAccountId != null &&
    settings.targetAccountId != null &&
    settings.sourceAccountId === settings.targetAccountId;

  const notEnoughAccess = !loading && accounts.length < 2;

  const canNext =
    settings.sourceAccountId != null &&
    settings.targetAccountId != null &&
    !sameAccount &&
    !notEnoughAccess;

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold">Шаг 1. Аккаунты</h3>
        <p className="text-sm text-muted-foreground">
          Выберите аккаунт-донор (откуда отгружать) и аккаунт-получатель (куда). Нужен доступ к обоим.
        </p>
      </div>

      {notEnoughAccess && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Недостаточно аккаунтов</AlertTitle>
          <AlertDescription>
            Для балансировки нужен доступ как минимум к двум аккаунтам WB.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label className="flex items-center gap-2"><Store className="h-4 w-4" /> Донор (откуда)</Label>
          <Select
            value={settings.sourceAccountId != null ? String(settings.sourceAccountId) : ""}
            onValueChange={(v) => onChange({ sourceAccountId: v ? Number(v) : null })}
            disabled={loading}
          >
            <SelectTrigger><SelectValue placeholder={loading ? "Загрузка…" : "Выберите аккаунт"} /></SelectTrigger>
            <SelectContent>
              {accounts.map((a) => (
                <SelectItem key={a.id} value={String(a.id)}>{a.name || `#${a.id}`}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="flex items-center gap-2"><Store className="h-4 w-4" /> Получатель (куда)</Label>
          <Select
            value={settings.targetAccountId != null ? String(settings.targetAccountId) : ""}
            onValueChange={(v) => onChange({ targetAccountId: v ? Number(v) : null })}
            disabled={loading}
          >
            <SelectTrigger><SelectValue placeholder={loading ? "Загрузка…" : "Выберите аккаунт"} /></SelectTrigger>
            <SelectContent>
              {accounts.map((a) => (
                <SelectItem key={a.id} value={String(a.id)}>{a.name || `#${a.id}`}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {sameAccount && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>Донор и получатель должны быть разными аккаунтами.</AlertDescription>
        </Alert>
      )}

      {canNext && (
        <Card className="bg-muted/30">
          <CardContent className="p-3 text-sm flex items-center justify-center gap-3">
            <span className="font-semibold">{accountName(settings.sourceAccountId)}</span>
            <ArrowRightLeft className="h-4 w-4 text-muted-foreground" />
            <span className="font-semibold">{accountName(settings.targetAccountId)}</span>
          </CardContent>
        </Card>
      )}

      <NavButtons canNext={canNext} onNext={onNext} />
    </div>
  );
}

// ─── Step 2: Preview ─────────────────────────────────────────────────
function buildPreviewBody(s: Settings) {
  return {
    account_id: s.sourceAccountId,
    kind: "store_balance",
    source_account_id: s.sourceAccountId,
    target_account_id: s.targetAccountId,
  };
}

function Step2Preview({
  settings, preview, setPreview, onBack, onNext,
}: {
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
        body: buildPreviewBody(settings),
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
          <h3 className="text-base font-semibold">Шаг 2. Превью</h3>
          <p className="text-sm text-muted-foreground">Сравниваем остатки и общие SKU между аккаунтами.</p>
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
            <MiniStat label="SKU донора" value={preview.source_skus_count} />
            <MiniStat label="SKU получателя" value={preview.target_skus_count} />
            <MiniStat label="Общие SKU" value={preview.shared_skus_count} />
            <MiniStat
              label="Излишек донора"
              value={preview.source_excess_units}
              tone={preview.source_excess_units ? "warning" : "default"}
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

// ─── Step 3: Params ──────────────────────────────────────────────────
function Step3Params({
  settings, onChange, onBack, onNext,
}: {
  settings: Settings;
  onChange: (p: Partial<Settings>) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const [nmInput, setNmInput] = useState("");
  const addNm = () => {
    const t = nmInput.trim();
    if (!t || settings.excludedNmIds.includes(t)) { setNmInput(""); return; }
    onChange({ excludedNmIds: [...settings.excludedNmIds, t] });
    setNmInput("");
  };

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold">Шаг 3. Параметры балансировки</h3>
        <p className="text-sm text-muted-foreground">Настройте режим и защитные пороги.</p>
      </div>

      <div className="space-y-1.5">
        <Label>Режим</Label>
        <Select value={settings.mode} onValueChange={(v) => onChange({ mode: v as BalanceMode })}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="donor_recipient">Donor → Recipient (покрыть дефицит получателя)</SelectItem>
            <SelectItem value="equalize">Equalize (выровнять остатки)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="sb-min-source">Минимум остатков донора</Label>
          <Input id="sb-min-source" type="number" min={0} step={1}
            value={settings.minSourceStock}
            onChange={(e) => onChange({ minSourceStock: Math.max(0, Number(e.target.value) || 0) })}
          />
          <p className="text-xs text-muted-foreground">Не отгружать ниже этого уровня.</p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sb-max-target">Максимум остатков получателя</Label>
          <Input id="sb-max-target" type="number" min={0} step={1}
            value={settings.maxTargetStock}
            onChange={(e) => onChange({ maxTargetStock: Math.max(0, Number(e.target.value) || 0) })}
          />
          <p className="text-xs text-muted-foreground">0 — без ограничения.</p>
        </div>
      </div>

      <Separator />

      <div className="flex items-center justify-between rounded-md border p-3">
        <div>
          <Label className="text-sm">Учитывать размеры</Label>
          <p className="text-xs text-muted-foreground">Балансировать в разрезе SKU+размер.</p>
        </div>
        <Switch checked={settings.sizeAware} onCheckedChange={(v) => onChange({ sizeAware: v })} />
      </div>

      <div className="space-y-1.5">
        <Label>Исключённые товары (nm_id)</Label>
        <div className="flex gap-2">
          <Input
            placeholder="Например: 12345678"
            value={nmInput}
            onChange={(e) => setNmInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addNm(); }}}
          />
          <Button type="button" variant="outline" onClick={addNm}>Добавить</Button>
        </div>
        {settings.excludedNmIds.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {settings.excludedNmIds.map((n) => (
              <Badge key={n} variant="secondary" className="gap-1 cursor-pointer"
                onClick={() => onChange({ excludedNmIds: settings.excludedNmIds.filter((x) => x !== n) })}>
                {n} ×
              </Badge>
            ))}
          </div>
        )}
      </div>

      <NavButtons onBack={onBack} canNext={true} onNext={onNext} />
    </div>
  );
}

// ─── Step 4: Run ─────────────────────────────────────────────────────
function buildRunBody(s: Settings) {
  return {
    account_id: s.sourceAccountId,
    run_type: "store_balance",
    target_account_id: s.targetAccountId,
    mode: s.mode,
    min_source_stock: s.minSourceStock,
    max_target_stock: s.maxTargetStock || null,
    size_aware: s.sizeAware,
    excluded_nm_ids: s.excludedNmIds.map((x) => Number(x)).filter((x) => !Number.isNaN(x)),
  };
}

function Step4Run({
  settings, runId, setRunId, onBack, onDone,
}: {
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
        body: buildRunBody(settings),
      }),
    onSuccess: (d) => {
      const id = (d as any)?.id ?? null;
      if (id != null) setRunId(id);
    },
  });

  const poll = useQuery({
    queryKey: ["stock-control-run", runId, "balance"],
    queryFn: () =>
      api<RunResp>(API_ENDPOINTS.portal.stockControlRunDetail(runId!), {
        query: { account_id: settings.sourceAccountId },
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
        <h3 className="text-base font-semibold">Шаг 4. Запуск балансировки</h3>
        <p className="text-sm text-muted-foreground">Расчёт выполняется на сервере.</p>
      </div>

      {runId == null && (
        <div className="space-y-3">
          {start.isError && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Не удалось запустить расчёт</AlertTitle>
              <AlertDescription>
                {start.error instanceof ApiError
                  ? start.error.message
                  : (start.error as Error).message}
              </AlertDescription>
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
function Step5Plan({
  sourceAccountId, runId, onRestart,
}: {
  sourceAccountId: number;
  runId: number | string;
  onRestart: () => void;
}) {
  const detail = useQuery({
    queryKey: ["stock-control-run", runId, "balance-detail"],
    queryFn: () =>
      api<RunResp>(API_ENDPOINTS.portal.stockControlRunDetail(runId), {
        query: { account_id: sourceAccountId },
      }),
    staleTime: 60_000,
  });

  const rows = useQuery<{ items?: any[] } | any[]>({
    queryKey: ["stock-control-run", runId, "balance-rows"],
    queryFn: () =>
      api(API_ENDPOINTS.portal.stockControlRunRows(runId), {
        query: { account_id: sourceAccountId, limit: 100 },
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
    return `${base}${API_ENDPOINTS.portal.stockControlRunExport(runId)}?account_id=${sourceAccountId}${
      token ? `&access_token=${encodeURIComponent(token)}` : ""
    }`;
  })();

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold flex items-center gap-2">
            <ArrowRightLeft className="h-4 w-4" /> План балансировки · #{runId}
          </h3>
          <p className="text-sm text-muted-foreground">
            Рекомендация по перемещению. Изменения в WB автоматически не применяются.
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
          <MiniStat label="К перемещению" value={summary.planned_units} />
          <MiniStat label="SKU" value={summary.skus_count} />
          <MiniStat label="Излишек донора" value={summary.source_excess_units} />
          <MiniStat label="Дефицит получателя" value={summary.target_shortage_units} tone="warning" />
          <MiniStat label="Не закрыто" value={summary.uncovered_units} tone="warning" />
        </div>
      ) : null}

      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold">Перемещения (первые 100)</div>
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
              Балансировка не выявила позиций для перемещения.
            </div>
          )}

          {!rows.isLoading && items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs uppercase text-muted-foreground border-b">
                    <th className="text-left py-1.5 pr-3">Товар</th>
                    <th className="text-left py-1.5 pr-3">Размер</th>
                    <th className="text-right py-1.5 pr-3">Остаток донора</th>
                    <th className="text-right py-1.5 pr-3">Остаток получателя</th>
                    <th className="text-right py-1.5 pr-3">Дефицит</th>
                    <th className="text-right py-1.5 pr-3">К перемещению</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((r: any, i: number) => (
                    <tr key={r.id ?? i} className="border-b last:border-0">
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
                        {r.source_stock_units != null ? formatNumber(r.source_stock_units) : "—"}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {r.target_stock_units != null ? formatNumber(r.target_stock_units) : "—"}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {r.target_shortage_units != null ? formatNumber(r.target_shortage_units) : "—"}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums font-semibold">
                        {r.planned_units != null ? formatNumber(r.planned_units) : "—"}
                      </td>
                    </tr>
                  ))}
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
  canNext, onNext, onBack,
}: { canNext?: boolean; onNext?: () => void; onBack?: () => void }) {
  return (
    <div className="flex justify-between pt-2">
      {onBack ? (
        <Button variant="outline" onClick={onBack}>
          <ChevronLeft className="h-4 w-4 mr-1" /> Назад
        </Button>
      ) : <div />}
      {onNext && (
        <Button onClick={onNext} disabled={!canNext}>
          Далее <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      )}
    </div>
  );
}
