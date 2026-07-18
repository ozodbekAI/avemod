// «Параметры» — настройки модуля Stock Control с валидацией и сохранением.
//
// GET  /portal/stock-control/settings?account_id=...   — загрузка текущих
// PUT  /portal/stock-control/settings?account_id=...   — сохранение
//
// Реальная схема бэкенда (StockControlSettingsRead/Update):
//   - minimum_history_orders:           int  >= 0    (default 10)
//   - max_share_ratio_from_default:     float >= 1   (default 3.0)
//   - minimum_keep_per_size:            int  >= 0    (default 0)
//   - excluded_regions_json:            string[]
//   - ship_all_available_default:       bool         (default false)
//   - extra_allocation_method_default:  "largest_remainder"
//   - default_il_profile_json:          { [warehouse: string]: number }
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, ApiError } from "@/lib/api";
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
import { Separator } from "@/components/ui/separator";
import {
  Save, AlertTriangle, CheckCircle2, Loader2, RotateCcw, Wrench, Settings as SettingsIcon, Trash2,
} from "lucide-react";
import { toast } from "sonner";

// ─── Schema (matches real backend) ───────────────────────────────────
const settingsSchema = z.object({
  minimum_history_orders: z.number().int().min(0, "Не может быть отрицательным").max(100000, "Слишком большое значение"),
  max_share_ratio_from_default: z.number().min(1, "Минимум 1.0").max(100, "Слишком большое значение"),
  minimum_keep_per_size: z.number().int().min(0, "Не может быть отрицательным").max(100000, "Слишком большое значение"),
  excluded_regions_json: z.array(z.string().trim().min(1).max(100)).max(100, "Не более 100 регионов"),
  ship_all_available_default: z.boolean(),
  extra_allocation_method_default: z.literal("largest_remainder"),
  default_il_profile_json: z.record(z.string().min(1), z.number().min(0, "Доли неотрицательные")),
});

type SettingsForm = z.infer<typeof settingsSchema>;

const DEFAULTS: SettingsForm = {
  minimum_history_orders: 10,
  max_share_ratio_from_default: 3.0,
  minimum_keep_per_size: 0,
  excluded_regions_json: [],
  ship_all_available_default: false,
  extra_allocation_method_default: "largest_remainder",
  default_il_profile_json: {},
};

function mergeWithDefaults(raw: any): SettingsForm {
  const src = (raw && typeof raw === "object" ? raw : {}) as Record<string, any>;
  const out: any = { ...DEFAULTS };
  for (const k of Object.keys(DEFAULTS)) {
    if (src[k] != null) out[k] = src[k];
  }
  out.excluded_regions_json = Array.isArray(out.excluded_regions_json)
    ? out.excluded_regions_json.map((x: any) => String(x)).filter(Boolean) : [];
  if (!out.default_il_profile_json || typeof out.default_il_profile_json !== "object" || Array.isArray(out.default_il_profile_json)) {
    out.default_il_profile_json = {};
  } else {
    const norm: Record<string, number> = {};
    for (const [k, v] of Object.entries(out.default_il_profile_json)) {
      const n = Number(v);
      if (k && Number.isFinite(n)) norm[String(k)] = n;
    }
    out.default_il_profile_json = norm;
  }
  if (out.extra_allocation_method_default !== "largest_remainder") {
    out.extra_allocation_method_default = "largest_remainder";
  }
  return out as SettingsForm;
}

// ─── Component ───────────────────────────────────────────────────────
export function SettingsTab({ accountId }: { accountId: number }) {
  const qc = useQueryClient();
  const queryKey = ["stock-control-settings", accountId];

  const q = useQuery({
    queryKey,
    queryFn: () =>
      api<any>(API_ENDPOINTS.portal.stockControlSettings, {
        query: { account_id: accountId },
      }),
    staleTime: 60_000,
    retry: false,
  });

  const [form, setForm] = useState<SettingsForm>(DEFAULTS);
  const [original, setOriginal] = useState<SettingsForm>(DEFAULTS);
  const [errors, setErrors] = useState<Partial<Record<keyof SettingsForm, string>>>({});
  const [regionInput, setRegionInput] = useState("");
  const [ilWhInput, setIlWhInput] = useState("");
  const [ilShareInput, setIlShareInput] = useState("");

  useEffect(() => {
    if (q.data) {
      const merged = mergeWithDefaults(q.data);
      setForm(merged);
      setOriginal(merged);
      setErrors({});
    }
  }, [q.data]);

  const patch = (p: Partial<SettingsForm>) => {
    setForm((f) => {
      const next = { ...f, ...p };
      const r = settingsSchema.safeParse(next);
      if (r.success) {
        setErrors({});
      } else {
        const e: any = {};
        for (const issue of r.error.issues) {
          const key = issue.path[0] as keyof SettingsForm;
          if (!e[key]) e[key] = issue.message;
        }
        setErrors(e);
      }
      return next;
    });
  };

  const isDirty = useMemo(() => JSON.stringify(form) !== JSON.stringify(original), [form, original]);
  const hasErrors = Object.keys(errors).length > 0;

  const save = useMutation({
    mutationFn: async () => {
      const parsed = settingsSchema.parse(form);
      return api<any>(API_ENDPOINTS.portal.stockControlSettings, {
        method: "PUT",
        query: { account_id: accountId },
        body: parsed,
      });
    },
    onSuccess: (data) => {
      const merged = mergeWithDefaults(data ?? form);
      setForm(merged);
      setOriginal(merged);
      toast.success("Параметры сохранены");
      qc.invalidateQueries({ queryKey });
    },
    onError: (e) => {
      const msg = e instanceof ApiError ? e.message : (e as Error).message;
      toast.error("Не удалось сохранить", { description: msg });
    },
  });

  const reset = () => {
    setForm(original);
    setErrors({});
  };

  // ─── Region helpers ──
  const addRegion = () => {
    const t = regionInput.trim();
    if (!t) return;
    if (t.length > 100) { toast.error("Название региона слишком длинное"); return; }
    if (form.excluded_regions_json.includes(t)) { setRegionInput(""); return; }
    if (form.excluded_regions_json.length >= 100) { toast.error("Не более 100 регионов"); return; }
    patch({ excluded_regions_json: [...form.excluded_regions_json, t] });
    setRegionInput("");
  };
  const removeRegion = (r: string) =>
    patch({ excluded_regions_json: form.excluded_regions_json.filter((x) => x !== r) });

  // ─── Default IL profile helpers ──
  const addIlEntry = () => {
    const wh = ilWhInput.trim();
    const share = Number(ilShareInput);
    if (!wh) { toast.error("Укажите склад"); return; }
    if (!Number.isFinite(share) || share < 0) { toast.error("Доля должна быть ≥ 0"); return; }
    patch({ default_il_profile_json: { ...form.default_il_profile_json, [wh]: share } });
    setIlWhInput("");
    setIlShareInput("");
  };
  const removeIlEntry = (wh: string) => {
    const next = { ...form.default_il_profile_json };
    delete next[wh];
    patch({ default_il_profile_json: next });
  };
  const updateIlEntry = (wh: string, val: string) => {
    const n = Number(val);
    if (!Number.isFinite(n)) return;
    patch({ default_il_profile_json: { ...form.default_il_profile_json, [wh]: n } });
  };

  // ─── Render ──
  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-4 md:p-6 space-y-4">
          <Skeleton className="h-6 w-48" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-16" />)}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (q.isError) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Не удалось загрузить параметры</AlertTitle>
        <AlertDescription className="space-y-2">
          <div>{(q.error as Error).message}</div>
          <Button size="sm" variant="outline" onClick={() => q.refetch()}>Повторить</Button>
        </AlertDescription>
      </Alert>
    );
  }

  const ilEntries = Object.entries(form.default_il_profile_json);

  return (
    <Card>
      <CardContent className="p-4 md:p-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h3 className="text-base font-semibold flex items-center gap-2">
              <SettingsIcon className="h-4 w-4" /> Параметры модуля
            </h3>
            <p className="text-sm text-muted-foreground">
              Значения по умолчанию для расчётов «Возврат лишнего» и «Поставка по регионам».
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline" size="sm"
              onClick={reset}
              disabled={!isDirty || save.isPending}
            >
              <RotateCcw className="h-3 w-3 mr-1" /> Отменить
            </Button>
            <Button
              size="sm"
              onClick={() => save.mutate()}
              disabled={!isDirty || hasErrors || save.isPending}
            >
              {save.isPending ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Save className="h-3 w-3 mr-1" />}
              Сохранить
            </Button>
          </div>
        </div>

        {hasErrors && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Исправьте ошибки перед сохранением</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-5 text-sm space-y-0.5">
                {Object.entries(errors).map(([k, msg]) => <li key={k}>{String(msg)}</li>)}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        {!isDirty && !save.isPending && q.data && (
          <div className="flex items-center gap-2 text-xs text-success">
            <CheckCircle2 className="h-3 w-3" /> Изменений нет — параметры синхронизированы с сервером.
          </div>
        )}

        <Separator />

        {/* Section: расчёт спроса */}
        <Section title="Расчёт спроса">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field
              label="Минимум заказов в истории"
              hint="SKU с числом заказов ниже порога не участвуют в расчёте спроса"
              error={errors.minimum_history_orders}
            >
              <Input
                type="number" min={0} max={100000} step={1}
                value={form.minimum_history_orders}
                onChange={(e) => patch({ minimum_history_orders: Math.floor(Number(e.target.value) || 0) })}
              />
            </Field>
            <Field
              label="Минимум остатка на размер"
              hint="Сколько штук каждого размера обязательно держать в магазине"
              error={errors.minimum_keep_per_size}
            >
              <Input
                type="number" min={0} max={100000} step={1}
                value={form.minimum_keep_per_size}
                onChange={(e) => patch({ minimum_keep_per_size: Math.floor(Number(e.target.value) || 0) })}
              />
            </Field>
          </div>
        </Section>

        {/* Section: распределение */}
        <Section title="Распределение и поставки">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field
              label="Max доля от справедливой (× от 1.0)"
              hint="Во сколько раз получатель может превысить свою справедливую долю"
              error={errors.max_share_ratio_from_default}
            >
              <Input
                type="number" min={1} max={100} step={0.1}
                value={form.max_share_ratio_from_default}
                onChange={(e) => patch({ max_share_ratio_from_default: Number(e.target.value) || 1 })}
              />
            </Field>
            <Field label="Метод распределения остатка">
              <Select
                value={form.extra_allocation_method_default}
                onValueChange={(v) =>
                  patch({ extra_allocation_method_default: v as SettingsForm["extra_allocation_method_default"] })
                }
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="largest_remainder">Largest remainder (Hamilton)</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          </div>

          <ToggleRow
            label="Отгружать всё доступное по умолчанию"
            hint="Если включено — алгоритм отгружает все доступные излишки, не оставляя резерва."
            checked={form.ship_all_available_default}
            onChange={(v) => patch({ ship_all_available_default: v })}
          />
        </Section>

        {/* Section: исключения */}
        <Section title="Исключения">
          <Field
            label="Исключённые регионы"
            hint="Эти регионы не участвуют в распределении"
            error={errors.excluded_regions_json}
          >
            <div className="flex gap-2">
              <Input
                placeholder="Например: Калининград"
                maxLength={100}
                value={regionInput}
                onChange={(e) => setRegionInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addRegion(); }}}
              />
              <Button type="button" variant="outline" onClick={addRegion}>Добавить</Button>
            </div>
            {form.excluded_regions_json.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-2">
                {form.excluded_regions_json.map((r) => (
                  <Badge key={r} variant="secondary" className="gap-1 cursor-pointer"
                    onClick={() => removeRegion(r)}>
                    {r} ×
                  </Badge>
                ))}
              </div>
            )}
          </Field>
        </Section>

        {/* Section: Default IL profile */}
        <Section title="Default ИЛ-профиль (склад → доля)">
          <p className="text-xs text-muted-foreground">
            Распределение по складам отгрузки, когда у магазина нет собственной истории.
            Доли — произвольные числа (например, веса), бэкенд нормализует их при расчёте.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-[1fr_160px_auto] gap-2">
            <Input
              placeholder="Склад (напр. Коледино)"
              maxLength={100}
              value={ilWhInput}
              onChange={(e) => setIlWhInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addIlEntry(); }}}
            />
            <Input
              type="number" min={0} step={0.1}
              placeholder="Доля"
              value={ilShareInput}
              onChange={(e) => setIlShareInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addIlEntry(); }}}
            />
            <Button type="button" variant="outline" onClick={addIlEntry}>Добавить</Button>
          </div>
          {errors.default_il_profile_json && (
            <p className="text-xs text-destructive">{String(errors.default_il_profile_json)}</p>
          )}
          {ilEntries.length > 0 && (
            <div className="space-y-1.5 pt-2">
              {ilEntries.map(([wh, share]) => (
                <div key={wh} className="flex items-center gap-2">
                  <div className="flex-1 text-sm font-medium truncate">{wh}</div>
                  <Input
                    type="number" min={0} step={0.1}
                    className="w-32"
                    value={share}
                    onChange={(e) => updateIlEntry(wh, e.target.value)}
                  />
                  <Button
                    type="button" variant="ghost" size="icon"
                    onClick={() => removeIlEntry(wh)}
                    aria-label={`Удалить ${wh}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* Footer save bar */}
        <div className="flex items-center justify-between pt-2 border-t">
          <div className="text-xs text-muted-foreground flex items-center gap-2">
            <Wrench className="h-3 w-3" />
            Account ID: {accountId}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline" size="sm"
              onClick={reset}
              disabled={!isDirty || save.isPending}
            >
              <RotateCcw className="h-3 w-3 mr-1" /> Отменить
            </Button>
            <Button
              size="sm"
              onClick={() => save.mutate()}
              disabled={!isDirty || hasErrors || save.isPending}
            >
              {save.isPending ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Save className="h-3 w-3 mr-1" />}
              Сохранить
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Small UI helpers ───────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">{title}</h4>
      {children}
    </div>
  );
}

function Field({
  label, hint, error, children,
}: { label: string; hint?: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm">{label}</Label>
      {children}
      {hint && !error && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

function ToggleRow({
  label, hint, checked, onChange,
}: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-start justify-between rounded-md border p-3 gap-3">
      <div className="space-y-0.5">
        <Label className="text-sm">{label}</Label>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}
