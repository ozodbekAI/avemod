// @ts-nocheck
// «Возврат лишнего» aligned with the TZOSTATKA operator flow:
// Excel/Finance source -> preview -> parameters -> run -> rows/movements/export.
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { API_ENDPOINTS } from "@/lib/endpoints";
import { useDateRange } from "@/lib/date-range-context";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  FileUp,
  Loader2,
  Play,
  RotateCcw,
  Undo2,
} from "lucide-react";
import { formatDateTime, formatNumber } from "@/lib/format";

type SourceMode = "finance_db" | "regional_supply_import";
type RunStatus =
  | "queued"
  | "running"
  | "completed"
  | "partial"
  | "failed"
  | "cancelled";
type JsonRecord = Record<string, unknown>;

interface ImportPreview {
  file_name: string;
  sheet_name?: string | null;
  rows_total: number;
  products: number;
  regions: number;
  sizes: number;
  warnings?: string[];
  sample_rows?: JsonRecord[];
}

interface ImportResult {
  id?: number | string;
  upload_id?: number | string;
  file_name?: string | null;
  rows_total?: number;
  metadata_json?: JsonRecord;
}

interface Settings {
  sourceMode: SourceMode;
  importId: number | string | null;
  fileName: string | null;
  dateFrom: string;
  dateTo: string;
  excludedRegions: string[];
  sizeAware: boolean;
  minimumKeepPerSize: number;
  allocationMode: "redistribute" | "balance";
  priorityStrategy: "dense" | "competition" | "sequential_with_secondary_sort";
}

interface RunResp {
  id: number | string;
  status: RunStatus;
  run_type?: string;
  source_mode?: string;
  allocation_mode?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  input_summary_json?: JsonRecord;
  result_summary_json?: JsonRecord;
  error_summary?: string | null;
  created_at?: string;
  finished_at?: string | null;
}

const STATUS_META: Record<string, { label: string; cls: string }> = {
  queued: {
    label: "В очереди",
    cls: "bg-muted text-muted-foreground border-border",
  },
  running: {
    label: "Выполняется",
    cls: "bg-primary/10 text-primary border-primary/30",
  },
  completed: {
    label: "Готово",
    cls: "bg-success/10 text-success border-success/30",
  },
  partial: {
    label: "Готово с предупреждениями",
    cls: "bg-warning/10 text-warning border-warning/30",
  },
  failed: {
    label: "Ошибка",
    cls: "bg-destructive/10 text-destructive border-destructive/30",
  },
  cancelled: {
    label: "Отменён",
    cls: "bg-muted text-muted-foreground border-border",
  },
};

const HUMAN_WARN: Record<string, string> = {
  empty_file: "Файл пустой или строки не распознаны.",
  missing_region: "Не найдена колонка региона.",
  missing_vendor_code: "Не найдена колонка артикула продавца.",
  stock_snapshot_missing:
    "Нет снимка остатков Finance для выбранного аккаунта.",
  warehouse_mapping_incomplete: "Не все склады сопоставлены с регионами.",
};

const humanize = (s: string) => HUMAN_WARN[s] ?? s;

export function ReturnWizard({ accountId }: { accountId: number }) {
  const dr = useDateRange();
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [runId, setRunId] = useState<number | string | null>(null);
  const [settings, setSettings] = useState<Settings>({
    sourceMode: "regional_supply_import",
    importId: null,
    fileName: null,
    dateFrom: dr.from,
    dateTo: dr.to,
    excludedRegions: [],
    sizeAware: true,
    minimumKeepPerSize: 1,
    allocationMode: "redistribute",
    priorityStrategy: "dense",
  });

  const patch = (p: Partial<Settings>) => setSettings((s) => ({ ...s, ...p }));
  const restart = () => {
    setStep(1);
    setPreview(null);
    setRunId(null);
    patch({ importId: null, fileName: null });
  };

  return (
    <Card>
      <CardContent className="space-y-6 p-4 md:p-6">
        <StepBar step={step} />
        {step === 1 && (
          <Step1Source
            accountId={accountId}
            settings={settings}
            onChange={patch}
            preview={preview}
            setPreview={setPreview}
            onNext={() => setStep(2)}
          />
        )}
        {step === 2 && (
          <Step2Params
            preview={preview}
            settings={settings}
            onChange={patch}
            onBack={() => setStep(1)}
            onNext={() => setStep(3)}
          />
        )}
        {step === 3 && (
          <Step3Confirm
            accountId={accountId}
            preview={preview}
            settings={settings}
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
          <Step5Results
            accountId={accountId}
            runId={runId}
            onRestart={restart}
          />
        )}
      </CardContent>
    </Card>
  );
}

function StepBar({ step }: { step: 1 | 2 | 3 | 4 | 5 }) {
  const labels = ["Источник", "Параметры", "Проверка", "Запуск", "Результат"];
  return (
    <div className="flex items-center gap-2 overflow-x-auto">
      {labels.map((label, i) => {
        const n = (i + 1) as 1 | 2 | 3 | 4 | 5;
        const active = n === step;
        const done = n < step;
        return (
          <div key={label} className="flex shrink-0 items-center gap-2">
            <div
              className={[
                "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold",
                active && "border-primary bg-primary text-primary-foreground",
                done && "border-success/30 bg-success/15 text-success",
                !active &&
                  !done &&
                  "border-border bg-muted text-muted-foreground",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {done ? <CheckCircle2 className="h-4 w-4" /> : n}
            </div>
            <span
              className={
                active
                  ? "whitespace-nowrap text-xs font-semibold"
                  : "whitespace-nowrap text-xs text-muted-foreground"
              }
            >
              {label}
            </span>
            {i < labels.length - 1 && (
              <ChevronRight className="h-3 w-3 text-muted-foreground" />
            )}
          </div>
        );
      })}
    </div>
  );
}

function Step1Source({
  accountId,
  settings,
  onChange,
  preview,
  setPreview,
  onNext,
}: {
  accountId: number;
  settings: Settings;
  onChange: (p: Partial<Settings>) => void;
  preview: ImportPreview | null;
  setPreview: (p: ImportPreview | null) => void;
  onNext: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setUploading(true);
    setError(null);
    setPreview(null);
    onChange({
      importId: null,
      fileName: file.name,
      sourceMode: "regional_supply_import",
    });
    try {
      const previewForm = new FormData();
      previewForm.append("file", file);
      const nextPreview = await api<ImportPreview>(
        API_ENDPOINTS.portal.stockControlImportRegionalSupplyPreview,
        {
          method: "POST",
          query: { account_id: accountId },
          formData: previewForm,
        },
      );
      setPreview(nextPreview);

      const importForm = new FormData();
      importForm.append("file", file);
      const imported = await api<ImportResult>(
        API_ENDPOINTS.portal.stockControlImportRegionalSupply,
        {
          method: "POST",
          query: { account_id: accountId },
          formData: importForm,
        },
      );
      const id = imported.upload_id ?? imported.id ?? null;
      if (id == null) throw new Error("Сервер не вернул import id");
      onChange({ importId: id, fileName: imported.file_name ?? file.name });
      toast.success("Excel-файл принят");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const canNext =
    settings.sourceMode === "finance_db" || settings.importId != null;

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold">Шаг 1. Источник данных</h3>
        <p className="text-sm text-muted-foreground">
          Загрузите Excel Wildberries как в TZOSTATKA или запустите расчёт по
          данным Finance.
        </p>
      </div>

      <RadioGroup
        value={settings.sourceMode}
        onValueChange={(v) => onChange({ sourceMode: v as SourceMode })}
        className="grid gap-2 md:grid-cols-2"
      >
        <SourceOption
          value="regional_supply_import"
          icon={<FileUp className="h-4 w-4" />}
          title="Excel Wildberries"
          desc="Файл «Поставка по регионам» / лист «Детальные данные»."
        />
        <SourceOption
          value="finance_db"
          icon={<Database className="h-4 w-4" />}
          title="Данные Finance"
          desc="Спрос и остатки из синхронизированной базы Finance."
        />
      </RadioGroup>

      {settings.sourceMode === "regional_supply_import" && (
        <div className="space-y-3 rounded-md border p-3">
          <Label className="flex items-center gap-2 text-sm">
            <FileUp className="h-4 w-4" />
            Основной WB-файл (.xlsx или .csv)
          </Label>
          <Input
            type="file"
            accept=".xlsx,.csv"
            disabled={uploading}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFile(f);
            }}
          />
          {uploading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              Проверка и импорт файла...
            </div>
          )}
          {error && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          {preview && <PreviewBlock preview={preview} />}
        </div>
      )}

      {settings.sourceMode === "finance_db" && (
        <Alert>
          <Database className="h-4 w-4" />
          <AlertTitle>Источник Finance</AlertTitle>
          <AlertDescription>
            Расчёт возьмёт спрос за выбранный период и последний снимок остатков
            для текущего аккаунта.
          </AlertDescription>
        </Alert>
      )}

      <NavButtons canNext={canNext} onNext={onNext} />
    </div>
  );
}

function SourceOption({
  value,
  icon,
  title,
  desc,
}: {
  value: string;
  icon: React.ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <Label
      htmlFor={`return-src-${value}`}
      className="flex cursor-pointer items-start gap-3 rounded-md border p-3 hover:bg-accent/40"
    >
      <RadioGroupItem
        id={`return-src-${value}`}
        value={value}
        className="mt-1"
      />
      <div className="space-y-0.5">
        <div className="flex items-center gap-2 text-sm font-medium">
          {icon}
          {title}
        </div>
        <div className="text-xs text-muted-foreground">{desc}</div>
      </div>
    </Label>
  );
}

function PreviewBlock({ preview }: { preview: ImportPreview }) {
  const rows = preview.sample_rows ?? [];
  return (
    <div className="space-y-3">
      <div className="grid gap-2 rounded-md border bg-muted/30 p-3 text-xs sm:grid-cols-5">
        <PreviewField label="Файл" value={preview.file_name} />
        <PreviewField label="Лист" value={preview.sheet_name ?? "-"} />
        <PreviewField label="Строк" value={formatNumber(preview.rows_total)} />
        <PreviewField
          label="Артикулов"
          value={formatNumber(preview.products)}
        />
        <PreviewField label="Регионов" value={formatNumber(preview.regions)} />
      </div>
      {Array.isArray(preview.warnings) && preview.warnings.length > 0 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Предупреждения файла</AlertTitle>
          <AlertDescription>
            <ul className="list-disc space-y-0.5 pl-5 text-sm">
              {preview.warnings.map((w) => (
                <li key={w}>{humanize(w)}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs">
            <thead className="bg-muted/60">
              <tr>
                <th className="px-2 py-1.5 text-left">Артикул</th>
                <th className="px-2 py-1.5 text-left">nm_id</th>
                <th className="px-2 py-1.5 text-left">Размер</th>
                <th className="px-2 py-1.5 text-left">Регион</th>
                <th className="px-2 py-1.5 text-right">Заказы</th>
                <th className="px-2 py-1.5 text-right">Остаток WB</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 10).map((row, i) => (
                <tr key={i} className="border-t">
                  <td className="px-2 py-1.5">
                    {String(row.vendor_code ?? "-")}
                  </td>
                  <td className="px-2 py-1.5">{String(row.nm_id ?? "-")}</td>
                  <td className="px-2 py-1.5">
                    {String(row.size_name ?? "-")}
                  </td>
                  <td className="px-2 py-1.5">{String(row.region ?? "-")}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {formatNumber(row.orders_qty ?? 0)}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {formatNumber(row.stock_qty ?? 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PreviewField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="truncate font-medium">{value}</div>
    </div>
  );
}

function Step2Params({
  preview,
  settings,
  onChange,
  onBack,
  onNext,
}: {
  preview: ImportPreview | null;
  settings: Settings;
  onChange: (p: Partial<Settings>) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const [regionInput, setRegionInput] = useState("");
  const addRegion = (region = regionInput) => {
    const value = region.trim();
    if (!value || settings.excludedRegions.includes(value)) {
      setRegionInput("");
      return;
    }
    onChange({ excludedRegions: [...settings.excludedRegions, value] });
    setRegionInput("");
  };
  const removeRegion = (region: string) =>
    onChange({
      excludedRegions: settings.excludedRegions.filter(
        (item) => item !== region,
      ),
    });
  const canNext =
    !!settings.dateFrom &&
    !!settings.dateTo &&
    settings.dateFrom <= settings.dateTo;
  const previewRegions = Array.from(
    new Set(
      (preview?.sample_rows ?? [])
        .map((row) => String(row.region ?? "").trim())
        .filter(Boolean),
    ),
  );

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold">Шаг 2. Параметры расчёта</h3>
        <p className="text-sm text-muted-foreground">
          Период спроса, исключения и правила удержания остатков.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="return-from">Период с</Label>
          <Input
            id="return-from"
            type="date"
            value={settings.dateFrom}
            onChange={(e) => onChange({ dateFrom: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="return-to">Период по</Label>
          <Input
            id="return-to"
            type="date"
            value={settings.dateTo}
            onChange={(e) => onChange({ dateTo: e.target.value })}
          />
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Режим распределения</Label>
          <Select
            value={settings.allocationMode}
            onValueChange={(v) =>
              onChange({ allocationMode: v as Settings["allocationMode"] })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="redistribute">
                Перераспределить излишки
              </SelectItem>
              <SelectItem value="balance">Балансировать остатки</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>Стратегия приоритета</Label>
          <Select
            value={settings.priorityStrategy}
            onValueChange={(v) =>
              onChange({ priorityStrategy: v as Settings["priorityStrategy"] })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="dense">Плотный рейтинг</SelectItem>
              <SelectItem value="competition">Конкурентный рейтинг</SelectItem>
              <SelectItem value="sequential_with_secondary_sort">
                Последовательно + сортировка
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Separator />

      <div className="flex items-center justify-between gap-4">
        <div>
          <Label className="text-sm">Учитывать размеры</Label>
          <p className="text-xs text-muted-foreground">
            Если в файле есть размер, расчёт ведётся отдельно по размеру.
          </p>
        </div>
        <Switch
          checked={settings.sizeAware}
          onCheckedChange={(v) => onChange({ sizeAware: v })}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="return-min-keep">Минимум оставить на размер</Label>
        <Input
          id="return-min-keep"
          type="number"
          min={0}
          step={1}
          value={settings.minimumKeepPerSize}
          onChange={(e) =>
            onChange({
              minimumKeepPerSize: Math.max(0, Number(e.target.value) || 0),
            })
          }
        />
      </div>

      <div className="space-y-2">
        <Label>Исключённые регионы</Label>
        <div className="flex gap-2">
          <Input
            placeholder="Например: Дальний Восток"
            value={regionInput}
            onChange={(e) => setRegionInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addRegion();
              }
            }}
          />
          <Button type="button" variant="outline" onClick={() => addRegion()}>
            Добавить
          </Button>
        </div>
        {previewRegions.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {previewRegions.map((region) => (
              <Button
                key={region}
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => addRegion(region)}
              >
                {region}
              </Button>
            ))}
          </div>
        )}
        {settings.excludedRegions.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {settings.excludedRegions.map((region) => (
              <Badge
                key={region}
                variant="secondary"
                className="cursor-pointer gap-1"
                onClick={() => removeRegion(region)}
              >
                {region} x
              </Badge>
            ))}
          </div>
        )}
      </div>

      <NavButtons onBack={onBack} canNext={canNext} onNext={onNext} />
    </div>
  );
}

function Step3Confirm({
  accountId,
  preview,
  settings,
  onBack,
  onNext,
}: {
  accountId: number;
  preview: ImportPreview | null;
  settings: Settings;
  onBack: () => void;
  onNext: () => void;
}) {
  const status = useQuery({
    queryKey: ["stock-control-status-for-return", accountId],
    queryFn: () =>
      api<{
        warnings?: string[];
        products_analyzed?: number;
        regions_analyzed?: number;
        source_freshness?: {
          stock_snapshot_at?: string | null;
          regional_demand_at?: string | null;
        };
      }>(API_ENDPOINTS.portal.stockControlStatus, {
        query: { account_id: accountId },
      }),
    staleTime: 30_000,
  });
  const warnings = [
    ...(preview?.warnings ?? []),
    ...((status.data?.warnings as string[] | undefined) ?? []),
  ];

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold">
          Шаг 3. Проверка перед запуском
        </h3>
        <p className="text-sm text-muted-foreground">
          Проверьте источник, период и свежесть остатков.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <MiniStat
          label="Источник"
          value={
            settings.sourceMode === "regional_supply_import"
              ? "Excel"
              : "Finance"
          }
        />
        <MiniStat
          label="Строк в файле"
          value={
            settings.sourceMode === "regional_supply_import"
              ? preview?.rows_total
              : undefined
          }
        />
        <MiniStat
          label="Артикулов"
          value={
            settings.sourceMode === "regional_supply_import"
              ? preview?.products
              : status.data?.products_analyzed
          }
        />
        <MiniStat
          label="Регионов"
          value={
            settings.sourceMode === "regional_supply_import"
              ? preview?.regions
              : status.data?.regions_analyzed
          }
        />
      </div>

      <Card className="bg-muted/30">
        <CardContent className="space-y-1 p-3 text-xs">
          <div className="font-semibold uppercase tracking-wide text-muted-foreground">
            Свежесть Finance
          </div>
          <div>
            Снимок остатков:{" "}
            {status.data?.source_freshness?.stock_snapshot_at
              ? formatDateTime(status.data.source_freshness.stock_snapshot_at)
              : "-"}
          </div>
          <div>
            Региональный спрос:{" "}
            {status.data?.source_freshness?.regional_demand_at
              ? formatDateTime(status.data.source_freshness.regional_demand_at)
              : "-"}
          </div>
        </CardContent>
      </Card>

      {warnings.length > 0 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Предупреждения</AlertTitle>
          <AlertDescription>
            <ul className="list-disc space-y-0.5 pl-5 text-sm">
              {warnings.map((w, i) => (
                <li key={`${w}-${i}`}>{humanize(w)}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <NavButtons onBack={onBack} onNext={onNext} nextLabel="Запустить" />
    </div>
  );
}

function MiniStat({
  label,
  value,
}: {
  label: string;
  value?: string | number | null;
}) {
  return (
    <Card>
      <CardContent className="space-y-1 p-3">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        <div className="text-lg font-semibold tabular-nums">
          {typeof value === "number" ? formatNumber(value) : value || "-"}
        </div>
      </CardContent>
    </Card>
  );
}

function buildRunPayload(accountId: number, s: Settings) {
  return {
    account_id: accountId,
    run_type: "return_excess",
    source_mode: s.sourceMode,
    regional_supply_import_id:
      s.sourceMode === "regional_supply_import" ? s.importId : null,
    date_from: s.dateFrom || null,
    date_to: s.dateTo || null,
    allocation_mode: s.allocationMode,
    priority_strategy: s.priorityStrategy,
    size_aware: s.sizeAware,
    settings_override: {
      excluded_regions_json: s.excludedRegions,
      minimum_keep_per_size: s.minimumKeepPerSize,
    },
  };
}

function Step4Run({
  accountId,
  settings,
  runId,
  setRunId,
  onBack,
  onDone,
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
        body: buildRunPayload(accountId, settings),
      }),
    onSuccess: (data) => {
      setRunId(data.id);
      toast.success("Расчёт поставлен в очередь");
    },
  });

  const poll = useQuery({
    queryKey: ["stock-control-return-run", runId],
    queryFn: () =>
      api<RunResp>(API_ENDPOINTS.portal.stockControlRunDetail(runId!), {
        query: { account_id: accountId },
      }),
    enabled: runId != null,
    refetchInterval: (q) => {
      const s = (q.state.data as RunResp | undefined)?.status;
      return s === "completed" ||
        s === "partial" ||
        s === "failed" ||
        s === "cancelled"
        ? false
        : 2000;
    },
  });

  const status = poll.data?.status ?? (runId ? "queued" : null);
  const done = status === "completed" || status === "partial";

  useEffect(() => {
    if (done) onDone();
  }, [done, onDone]);

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold">Шаг 4. Запуск расчёта</h3>
        <p className="text-sm text-muted-foreground">
          Backend создаёт локальный run без изменений в WB.
        </p>
      </div>

      {runId == null && (
        <div className="space-y-3">
          {start.isError && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Не удалось запустить расчёт</AlertTitle>
              <AlertDescription>
                {(start.error as Error).message}
              </AlertDescription>
            </Alert>
          )}
          <Button
            onClick={() => start.mutate()}
            disabled={start.isPending}
            className="gap-2"
          >
            {start.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Запустить возврат
          </Button>
        </div>
      )}

      {runId != null && (
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center justify-between">
              <div className="text-sm">
                Расчёт <span className="font-mono">#{runId}</span>
              </div>
              <RunStatusBadge status={status} />
            </div>
            <Progress value={done ? 100 : status === "running" ? 55 : 10} />
            {poll.data?.error_summary && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Ошибка расчёта</AlertTitle>
                <AlertDescription>{poll.data.error_summary}</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      )}

      <div className="flex justify-between">
        <Button variant="outline" onClick={onBack} disabled={start.isPending}>
          <ChevronLeft className="mr-1 h-4 w-4" /> Назад
        </Button>
        {done && (
          <Button onClick={onDone}>
            К результату <ChevronRight className="ml-1 h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

function RunStatusBadge({ status }: { status: string | null }) {
  const meta = (status && STATUS_META[status]) || STATUS_META.queued;
  return (
    <Badge variant="outline" className={meta.cls}>
      {meta.label}
    </Badge>
  );
}

function Step5Results({
  accountId,
  runId,
  onRestart,
}: {
  accountId: number;
  runId: number | string;
  onRestart: () => void;
}) {
  const detail = useQuery({
    queryKey: ["stock-control-return-result", runId],
    queryFn: () =>
      api<RunResp>(API_ENDPOINTS.portal.stockControlRunDetail(runId), {
        query: { account_id: accountId },
      }),
    staleTime: 60_000,
  });
  const rows = useQuery<{ items?: JsonRecord[] } | JsonRecord[]>({
    queryKey: ["stock-control-return-rows", runId],
    queryFn: () =>
      api(API_ENDPOINTS.portal.stockControlRunRows(runId), {
        query: { account_id: accountId, limit: 100 },
      }),
    staleTime: 60_000,
  });
  const movements = useQuery<{ items?: JsonRecord[] } | JsonRecord[]>({
    queryKey: ["stock-control-return-movements", runId],
    queryFn: () =>
      api(API_ENDPOINTS.portal.stockControlRunMovements(runId), {
        query: { account_id: accountId, limit: 100 },
      }),
    staleTime: 60_000,
  });
  const rowItems = useMemo(() => normalizeItems(rows.data), [rows.data]);
  const movementItems = useMemo(
    () => normalizeItems(movements.data),
    [movements.data],
  );
  const summary = detail.data?.result_summary_json ?? {};

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold">
            <Undo2 className="h-4 w-4" />
            Результат возврата #{runId}
          </h3>
          <p className="text-sm text-muted-foreground">
            План возврата и перемещений. WB автоматически не меняется.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void downloadStockControlExport(accountId, runId)}
            className="gap-2"
          >
            <Download className="h-3 w-3" />
            Excel
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onRestart}
            className="gap-2"
          >
            <RotateCcw className="h-3 w-3" />
            Новый расчёт
          </Button>
        </div>
      </div>

      {detail.isLoading ? (
        <div className="grid gap-3 md:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-5">
          <MiniStat label="Избыток" value={summary.excess_units} />
          <MiniStat label="Дефицит" value={summary.shortage_units} />
          <MiniStat
            label="Переместить"
            value={summary.units_to_move ?? summary.movements}
          />
          <MiniStat label="Товаров" value={summary.products} />
          <MiniStat label="Регионов" value={summary.regions} />
        </div>
      )}

      <ResultTable
        title="Строки по регионам"
        loading={rows.isLoading}
        items={rowItems}
      />
      <MovementsTable loading={movements.isLoading} items={movementItems} />
    </div>
  );
}

function normalizeItems(data: unknown): JsonRecord[] {
  if (!data) return [];
  if (Array.isArray(data)) return data.filter(isRecord);
  if (isRecord(data) && Array.isArray(data.items)) {
    return data.items.filter(isRecord);
  }
  return [];
}

function isRecord(value: unknown): value is JsonRecord {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function ResultTable({
  title,
  loading,
  items,
}: {
  title: string;
  loading: boolean;
  items: JsonRecord[];
}) {
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">{title}</div>
          <div className="text-xs text-muted-foreground">
            {loading ? "Загрузка..." : `Показано: ${items.length}`}
          </div>
        </div>
        {loading && <Skeleton className="h-32" />}
        {!loading && items.length === 0 && (
          <div className="py-4 text-center text-sm text-muted-foreground">
            Нет строк для показа.
          </div>
        )}
        {!loading && items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-xs uppercase text-muted-foreground">
                  <th className="py-1.5 pr-3 text-left">Товар</th>
                  <th className="py-1.5 pr-3 text-left">Регион / склад</th>
                  <th className="py-1.5 pr-3 text-left">Размер</th>
                  <th className="py-1.5 pr-3 text-right">Заказы</th>
                  <th className="py-1.5 pr-3 text-right">Остаток</th>
                  <th className="py-1.5 text-right">Дельта</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row, i) => (
                  <tr key={row.id ?? i} className="border-b last:border-0">
                    <td className="py-1.5 pr-3">
                      {row.nm_id ? (
                        <Link
                          to="/products/$nmId"
                          params={{ nmId: String(row.nm_id) }}
                          className="text-primary hover:underline"
                        >
                          {row.vendor_code || row.nm_id}
                        </Link>
                      ) : (
                        row.vendor_code || "-"
                      )}
                    </td>
                    <td className="py-1.5 pr-3">
                      {row.region ?? row.warehouse_name ?? "-"}
                    </td>
                    <td className="py-1.5 pr-3">{row.size_name ?? "-"}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">
                      {formatNumber(row.orders_qty ?? 0)}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">
                      {formatNumber(row.current_stock_qty ?? 0)}
                    </td>
                    <td className="py-1.5 text-right tabular-nums font-semibold">
                      {formatNumber(row.delta_qty ?? 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MovementsTable({
  loading,
  items,
}: {
  loading: boolean;
  items: JsonRecord[];
}) {
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">План перемещений</div>
          <div className="text-xs text-muted-foreground">
            {loading ? "Загрузка..." : `Показано: ${items.length}`}
          </div>
        </div>
        {loading && <Skeleton className="h-32" />}
        {!loading && items.length === 0 && (
          <div className="py-4 text-center text-sm text-muted-foreground">
            Перемещения не сформированы.
          </div>
        )}
        {!loading && items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-xs uppercase text-muted-foreground">
                  <th className="py-1.5 pr-3 text-left">Товар</th>
                  <th className="py-1.5 pr-3 text-left">Откуда</th>
                  <th className="py-1.5 pr-3 text-left">Куда</th>
                  <th className="py-1.5 pr-3 text-left">Приоритет</th>
                  <th className="py-1.5 text-right">Кол-во</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row, i) => (
                  <tr key={row.id ?? i} className="border-b last:border-0">
                    <td className="py-1.5 pr-3">
                      {row.vendor_code || row.nm_id || "-"}
                    </td>
                    <td className="py-1.5 pr-3">
                      {row.donor_region ?? row.donor_warehouse ?? "-"}
                    </td>
                    <td className="py-1.5 pr-3">
                      {row.recipient_region ?? row.recipient_warehouse ?? "-"}
                    </td>
                    <td className="py-1.5 pr-3">{row.priority ?? "-"}</td>
                    <td className="py-1.5 text-right tabular-nums font-semibold">
                      {formatNumber(row.quantity ?? 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

async function downloadStockControlExport(
  accountId: number,
  runId: number | string,
) {
  try {
    const res = await api<{
      file_name: string;
      content_type: string;
      content_base64: string | null;
    }>(API_ENDPOINTS.portal.stockControlRunExport(runId), {
      query: { account_id: accountId },
    });
    if (!res.content_base64) throw new Error("Export artifact is empty");
    const raw = window.atob(res.content_base64);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
    const blob = new Blob([bytes], {
      type:
        res.content_type ||
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = res.file_name || `stock_control_return_${runId}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
    toast.success("Excel скачивается");
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Не удалось скачать Excel");
  }
}

function NavButtons({
  onBack,
  onNext,
  canNext = true,
  nextLabel = "Далее",
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
          <ChevronLeft className="mr-1 h-4 w-4" /> Назад
        </Button>
      ) : (
        <span />
      )}
      <Button onClick={onNext} disabled={!canNext}>
        {nextLabel} <ChevronRight className="ml-1 h-4 w-4" />
      </Button>
    </div>
  );
}
