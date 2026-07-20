import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { type BusinessSettingsResponse, type BusinessSettings } from "@/lib/api";
import { fetchBusinessSettings, patchBusinessSettings } from "@/lib/money-endpoints";
import { useAccounts } from "@/lib/account-context";
import { PageShell, PageHeader } from "@/components/PageShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";
import { Save, RotateCcw, Info, AlertTriangle, ArrowRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { EndpointError } from "@/components/EndpointError";
import { ModulesHealthSection } from "@/components/settings/ModulesHealthSection";
import { DataSyncSection } from "@/components/settings/DataSyncSection";

export const Route = createFileRoute("/_authenticated/settings")({
  component: SettingsPage,
  errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} />,
});

const COST_POLICY_DESC: Record<string, { label: string; description: string; impact: string }> = {
  supplier_only: {
    label: "Только поставщик",
    description: "Использовать только подтверждённую поставщиком себестоимость.",
    impact: "Если себестоимость поставщика не загружена — прибыль и закупки не считаются.",
  },
  operator_baseline: {
    label: "Оператор baseline",
    description: "Операторская себестоимость приемлема для бизнес-решений, но не является финальным подтверждением.",
    impact: "Прибыль и закупки считаются, но помечаются как предварительные.",
  },
  mixed: {
    label: "Смешанный",
    description: "Использовать поставщика где есть, иначе — оператор baseline.",
    impact: "Баланс между скоростью и точностью. Карточки без поставщика считаются по baseline.",
  },
};

function defaultSettings(): BusinessSettings {
  return {
    target_margin_rate: 0.2,
    target_roi_percent: 30,
    lead_time_days: 14,
    safety_days: 7,
    overstock_threshold_days: 90,
    oos_threshold_days: 7,
    min_profit_threshold: 1000,
    ad_drr_threshold_percent: 20,
    pack_multiple: 1,
    cost_trust_policy: "mixed",
    issue_aging: { pending_days: 3, warning_days: 7 },
  };
}

function SettingsPage() {
  const { activeId } = useAccounts();
  const qc = useQueryClient();
  const [form, setForm] = useState<BusinessSettings | null>(null);
  const [savedRecently, setSavedRecently] = useState(false);

  const settingsQ = useQuery({
    queryKey: ["business-settings", activeId],
    enabled: !!activeId,
    queryFn: () => fetchBusinessSettings(activeId!) as Promise<BusinessSettingsResponse>,
  });

  const policiesQ = useQuery({
    queryKey: ["business-settings-policies", activeId],
    enabled: !!activeId,
    queryFn: () =>
      fetchBusinessSettings(activeId!).then((r) => {
        const res = r as any;
        // If backend returns inline policies, use them; otherwise fallback to hardcoded.
        const policies = res?.policies?.cost_trust_policy ?? [
          { value: "supplier_only", label: "Только поставщик" },
          { value: "operator_baseline", label: "Оператор baseline" },
          { value: "mixed", label: "Смешанный" },
        ];
        return { cost_trust_policy: policies } as { cost_trust_policy: Array<{ value: string; label: string }> };
      }),
  });

  useEffect(() => {
    if (settingsQ.data?.settings && !form) {
      setForm({
        ...defaultSettings(),
        ...settingsQ.data.settings,
        issue_aging: {
          ...defaultSettings().issue_aging,
          ...(settingsQ.data.settings.issue_aging ?? {}),
        },
      });
    }
  }, [settingsQ.data, form]);

  const save = useMutation({
    mutationFn: (body: BusinessSettings) =>
      patchBusinessSettings(activeId!, body) as Promise<BusinessSettingsResponse>,
    onSuccess: () => {
      toast.success("Настройки сохранены");
      setSavedRecently(true);
      setTimeout(() => setSavedRecently(false), 8000);
      qc.invalidateQueries({ queryKey: ["business-settings", activeId] });
      qc.invalidateQueries({ queryKey: ["money-summary"] });
      qc.invalidateQueries({ queryKey: ["money-actions"] });
      qc.invalidateQueries({ queryKey: ["purchase-plan"] });
      qc.invalidateQueries({ queryKey: ["pricing-safety"] });
      qc.invalidateQueries({ queryKey: ["ads-efficiency"] });
      qc.invalidateQueries({ queryKey: ["finance-reconciliation"] });
    },
    onError: (e: any) => toast.error(`Ошибка: ${e.message}`),
  });

  // Detect dirty fields by comparing to the loaded baseline.
  const baseline = settingsQ.data?.settings;
  const dirtyKeys = useMemo(() => {
    if (!form || !baseline) return new Set<string>();
    const d = new Set<string>();
    for (const k of Object.keys(form) as Array<keyof BusinessSettings>) {
      if (JSON.stringify((form as any)[k]) !== JSON.stringify((baseline as any)[k])) d.add(String(k));
    }
    return d;
  }, [form, baseline]);
  const isDirty = dirtyKeys.size > 0;

  // Warn before leaving with unsaved changes
  useEffect(() => {
    if (!isDirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);

  if (!activeId)
    return (
      <PageShell>
        <PageHeader title="Настройки" />
        <Alert>
          <AlertTitle>Не выбран кабинет</AlertTitle>
          <AlertDescription>Выберите кабинет.</AlertDescription>
        </Alert>
      </PageShell>
    );

  if (settingsQ.isLoading || !form)
    return (
      <PageShell>
        <PageHeader title="Настройки" />
        <div className="grid gap-3 md:grid-cols-2">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      </PageShell>
    );

  const reset = () => {
    if (settingsQ.data?.settings) {
      setForm({
        ...defaultSettings(),
        ...settingsQ.data.settings,
        issue_aging: {
          ...defaultSettings().issue_aging,
          ...(settingsQ.data.settings.issue_aging ?? {}),
        },
      });
    }
  };
  const update = <K extends keyof BusinessSettings>(k: K, v: BusinessSettings[K]) =>
    setForm({ ...form, [k]: v });

  const lastUpdated = settingsQ.data?.updated_at;
  const lastComment = settingsQ.data?.comment;
  const visibleLastComment = settingsCommentLabel(lastComment);
  const currentPolicy = form.cost_trust_policy ?? "mixed";
  const policyMeta = COST_POLICY_DESC[currentPolicy] ?? COST_POLICY_DESC.mixed;

  return (
    <PageShell>
      <PageHeader
        title="Бизнес-настройки"
        description="Правила, по которым система рассчитывает прибыль, риски и закупки."
        actions={
          isDirty ? (
            <Badge variant="outline" className="bg-warning/10 text-warning border-warning/30">
              Изменений: {dirtyKeys.size}
            </Badge>
          ) : undefined
        }
      />

      {savedRecently && (
        <Alert className="mb-4 border-success/30 bg-success/5">
          <Info className="h-4 w-4 text-success" />
          <AlertTitle>Сохранено</AlertTitle>
          <AlertDescription>
            Пересчёт прибыли, безопасных цен, рекомендаций по закупкам и рекламе запущен.
            Обновление mart-таблиц и бизнес-действий может занять несколько минут.
          </AlertDescription>
        </Alert>
      )}

      {(lastUpdated || lastComment) && !isDirty && !savedRecently && (
        <Alert className="mb-4">
          <Info className="h-4 w-4" />
          <AlertTitle>История изменений</AlertTitle>
          <AlertDescription className="text-xs">
            {lastUpdated && (
              <>
                Последнее обновление: <b>{new Date(lastUpdated).toLocaleString("ru-RU")}</b>
              </>
            )}
            {visibleLastComment && (
              <div className="mt-1">
                Комментарий: <i>{visibleLastComment}</i>
              </div>
            )}
          </AlertDescription>
        </Alert>
      )}

      {isDirty && (
        <Alert className="mb-4 border-warning/30 bg-warning/5">
          <AlertTriangle className="h-4 w-4 text-warning" />
          <AlertTitle>Есть несохранённые изменения</AlertTitle>
          <AlertDescription>
            После сохранения система пересчитает прибыль, безопасные цены, рекомендации по закупкам и рекламу.
            Это может занять несколько минут.
          </AlertDescription>
        </Alert>
      )}

      <div className="mb-4">
        <DataSyncSection accountId={activeId} />
      </div>

      <ModulesHealthSection />

      {/* Profit & ROI */}
      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Цели прибыли и ROI</CardTitle>
          <CardDescription>Какую маржу и ROI считать достаточным.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field
            label="Целевая маржа"
            hint="Доля прибыли в выручке. 0.2 = 20%."
            dirty={dirtyKeys.has("target_margin_rate")}
          >
            <Input
              type="number"
              step="0.01"
              value={form.target_margin_rate}
              onChange={(e) => update("target_margin_rate", Number(e.target.value))}
            />
          </Field>
          <Field
            label="Целевой ROI, %"
            hint="Возврат на закупочную цену."
            dirty={dirtyKeys.has("target_roi_percent")}
          >
            <Input
              type="number"
              value={form.target_roi_percent}
              onChange={(e) => update("target_roi_percent", Number(e.target.value))}
            />
          </Field>
          <Field
            label="Минимальная прибыль (₽)"
            hint="Ниже этого порога карточка считается рискованной."
            dirty={dirtyKeys.has("min_profit_threshold")}
          >
            <Input
              type="number"
              value={form.min_profit_threshold}
              onChange={(e) => update("min_profit_threshold", Number(e.target.value))}
            />
          </Field>
          <Field
            label="Порог DRR рекламы, %"
            hint="Выше — реклама считается рискованной."
            dirty={dirtyKeys.has("ad_drr_threshold_percent")}
          >
            <Input
              type="number"
              value={form.ad_drr_threshold_percent}
              onChange={(e) => update("ad_drr_threshold_percent", Number(e.target.value))}
            />
          </Field>
        </CardContent>
      </Card>

      {/* Stock & Purchasing */}
      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Остатки и закупки</CardTitle>
          <CardDescription>Сроки поставки, страховой запас и пороги остатков.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field
            label="Срок поставки, дней"
            hint="Сколько дней идёт поставка."
            dirty={dirtyKeys.has("lead_time_days")}
          >
            <Input
              type="number"
              value={form.lead_time_days}
              onChange={(e) => update("lead_time_days", Number(e.target.value))}
            />
          </Field>
          <Field
            label="Страховой запас, дней"
            hint="Страховой запас сверх срока поставки."
            dirty={dirtyKeys.has("safety_days")}
          >
            <Input
              type="number"
              value={form.safety_days}
              onChange={(e) => update("safety_days", Number(e.target.value))}
            />
          </Field>
          <Field
            label="Сверхзапас, дней"
            hint="Дольше этого — считается замороженным."
            dirty={dirtyKeys.has("overstock_threshold_days")}
          >
            <Input
              type="number"
              value={form.overstock_threshold_days}
              onChange={(e) => update("overstock_threshold_days", Number(e.target.value))}
            />
          </Field>
          <Field
            label="Порог нехватки, дней"
            hint="Меньше этого — риск закончиться."
            dirty={dirtyKeys.has("oos_threshold_days")}
          >
            <Input
              type="number"
              value={form.oos_threshold_days}
              onChange={(e) => update("oos_threshold_days", Number(e.target.value))}
            />
          </Field>
          <Field
            label="Кратность закупки"
            hint="Минимальная единица закупки."
            dirty={dirtyKeys.has("pack_multiple")}
          >
            <Input
              type="number"
              value={form.pack_multiple}
              onChange={(e) => update("pack_multiple", Number(e.target.value))}
            />
          </Field>
        </CardContent>
      </Card>

      {/* Cost trust policy */}
      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Доверие к себестоимости</CardTitle>
          <CardDescription>Какую себестоимость система имеет право использовать.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Select value={currentPolicy} onValueChange={(v) => update("cost_trust_policy", v)}>
              <SelectTrigger className="flex-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(policiesQ.data?.cost_trust_policy ?? []).map((p) => (
                  <SelectItem key={p.value} value={p.value}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {dirtyKeys.has("cost_trust_policy") && (
              <Badge variant="outline" className="bg-warning/10 text-warning border-warning/30 text-[10px]">
                изменено
              </Badge>
            )}
          </div>

          {/* Policy explanation */}
          <div className="rounded-md border p-3 space-y-2">
            <div className="text-sm font-medium">{policyMeta.label}</div>
            <p className="text-xs text-muted-foreground">{policyMeta.description}</p>
            <Separator />
            <div className="flex items-start gap-2">
              <Info className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
              <p className="text-xs text-muted-foreground">{policyMeta.impact}</p>
            </div>
          </div>

          <Button asChild variant="outline" size="sm">
            <Link to="/costs">
              К себестоимости <ArrowRight className="h-3 w-3 ml-1" />
            </Link>
          </Button>
        </CardContent>
      </Card>

      {/* Issue aging */}
      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Старение проблем</CardTitle>
          <CardDescription>Через сколько дней проблема становится pending / warning.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field
            label="В ожидании после, дней"
            dirty={dirtyKeys.has("issue_aging")}
          >
            <Input
              type="number"
              value={form.issue_aging?.pending_days ?? 3}
              onChange={(e) =>
                setForm({
                  ...form,
                  issue_aging: {
                    ...(form.issue_aging ?? { pending_days: 3, warning_days: 7 }),
                    pending_days: Number(e.target.value),
                  },
                })
              }
            />
          </Field>
          <Field
            label="Предупреждение после, дней"
            dirty={dirtyKeys.has("issue_aging")}
          >
            <Input
              type="number"
              value={form.issue_aging?.warning_days ?? 7}
              onChange={(e) =>
                setForm({
                  ...form,
                  issue_aging: {
                    ...(form.issue_aging ?? { pending_days: 3, warning_days: 7 }),
                    warning_days: Number(e.target.value),
                  },
                })
              }
            />
          </Field>
        </CardContent>
      </Card>

      {/* Sticky save bar */}
      <div className="sticky bottom-4 z-10">
        <div
          className={`flex items-center gap-2 p-3 rounded-lg border shadow-md ${
            isDirty ? "bg-warning/10 border-warning/30" : "bg-card"
          }`}
        >
          <div className="flex-1 text-xs text-muted-foreground">
            {isDirty ? (
              <>
                Изменено полей: <b>{dirtyKeys.size}</b>. После сохранения — пересчёт mart-таблиц и действий.
              </>
            ) : (
              "Все изменения сохранены."
            )}
          </div>
          <Button variant="outline" onClick={reset} disabled={!isDirty || save.isPending}>
            <RotateCcw className="h-4 w-4 mr-1.5" /> Сбросить
          </Button>
          <Button onClick={() => save.mutate(form)} disabled={!isDirty || save.isPending}>
            {save.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
            ) : (
              <Save className="h-4 w-4 mr-1.5" />
            )}
            Сохранить
          </Button>
        </div>
      </div>
    </PageShell>
  );
}

function settingsCommentLabel(value: string | null | undefined): string | null {
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  if (raw.toLowerCase().includes("demo/test readiness")) {
    return "Демо-данные подтверждены для локального UI-аудита; видимые блокеры нужно закрыть для реалистичной проверки.";
  }
  return raw
    .replace(/\bdemo\b/gi, "демо")
    .replace(/\btest\b/gi, "тест")
    .replace(/\blocal data\b/gi, "локальные данные")
    .replace(/\bUI smoke\b/gi, "проверка интерфейса");
}

function Field({
  label,
  hint,
  dirty,
  children,
}: {
  label: string;
  hint?: string;
  dirty?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="flex items-center gap-1 text-sm">
        {label}
        {hint && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3 w-3 text-muted-foreground cursor-help" />
              </TooltipTrigger>
              <TooltipContent className="max-w-xs text-xs">{hint}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
        {dirty && (
          <Badge variant="outline" className="bg-warning/10 text-warning border-warning/30 text-[9px] uppercase ml-auto">
            изменено
          </Badge>
        )}
      </Label>
      {children}
    </div>
  );
}
