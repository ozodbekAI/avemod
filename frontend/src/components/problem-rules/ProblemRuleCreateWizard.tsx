import { useEffect, useMemo, useState, type ComponentType } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import {
  createProblemDefinition,
  createProblemRuleVersion,
  type MetricCatalogItem,
  type ProblemDefinition,
  type ProblemDefinitionCreatePayload,
  type ProblemRuleVersion,
  type ProblemRuleVersionCreatePayload,
} from "@/lib/problem-rules";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EvidenceTemplateEditor } from "./EvidenceTemplateEditor";
import { MetricChipGroups } from "./MetricChipGroups";
import {
  CATEGORY_LABELS,
  CATEGORY_OPTIONS,
  ENTITY_LABELS,
  ENTITY_OPTIONS,
  Field,
  IMPACT_LABELS,
  IMPACT_OPTIONS,
  InfoTile,
  SEVERITY_LABELS,
  SEVERITY_OPTIONS,
  TRUST_LABELS,
  TRUST_OPTIONS,
  TemplatePreview,
  type RuleBuilderState,
  optionText,
} from "./ProblemRulesAdminShared";
import { ScenarioTemplatePicker } from "./ScenarioTemplatePicker";
import {
  type HumanRuleFormula,
  VisualFormulaBuilder,
} from "./VisualFormulaBuilder";

type TemplateMeta = {
  impactTypeLabel?: string;
  trustLabel?: string;
  typicalActionLabel?: string;
  surfaceTag?: string;
  requiredMetrics?: string[];
};

// Spec-defined metadata per scenario template. Required metrics are shown as
// template requirements — they do not become selected metrics until the
// admin applies the template and the backend catalog actually contains them.
const TEMPLATE_METADATA: Record<string, TemplateMeta> = {
  missing_cost_blocks_profit: {
    impactTypeLabel: "Блокер данных",
    trustLabel: "Не хватает данных",
    typicalActionLabel: "Открыть исправление данных",
    surfaceTag: "Data Fix / Money / Action Center",
    requiredMetrics: ["revenue_30d", "cost_price"],
  },
  negative_unit_profit: {
    impactTypeLabel: "Вероятный убыток",
    trustLabel: "Оценка / Предварительно",
    typicalActionLabel: "Проверить цену / расходы",
    surfaceTag: "Money / Product360 / Action Center",
    requiredMetrics: ["price", "cost_price", "commission", "logistics", "ads_spend"],
  },
  overstock_slow_moving: {
    impactTypeLabel: "Заблокированные деньги",
    trustLabel: "Оценка",
    typicalActionLabel: "Проверить промо / цену",
    surfaceTag: "Product360 / Action Center",
    requiredMetrics: ["stock_qty", "avg_daily_sales", "days_of_stock", "cost_price"],
  },
  low_stock_risk: {
    impactTypeLabel: "Риск потери продаж",
    trustLabel: "Предварительно",
    typicalActionLabel: "Открыть план поставки",
    surfaceTag: "Product360 / Action Center",
    requiredMetrics: ["stock_qty", "avg_daily_sales", "days_of_stock"],
  },
  fast_stock_depletion: {
    impactTypeLabel: "Риск потери продаж",
    trustLabel: "Предварительно",
    typicalActionLabel: "Открыть план поставки",
    surfaceTag: "Product360 / Action Center",
    requiredMetrics: ["stock_qty", "avg_daily_sales", "days_of_stock"],
  },
  ads_spend_without_profit: {
    impactTypeLabel: "Вероятный убыток",
    trustLabel: "Оценка",
    typicalActionLabel: "Открыть рекламу / проверить карточку",
    surfaceTag: "Money / Product360 / Action Center",
    requiredMetrics: ["ad_spend", "revenue", "unit_profit_after_ads"],
  },
  promo_not_profitable: {
    impactTypeLabel: "Вероятный убыток",
    trustLabel: "Оценка",
    typicalActionLabel: "Проверить промо",
    surfaceTag: "Money / Product360",
    requiredMetrics: ["promo_price", "cost_price", "margin_pct"],
  },
  price_below_safe_margin: {
    impactTypeLabel: "Вероятный убыток",
    trustLabel: "Оценка",
    typicalActionLabel: "Проверить цену",
    surfaceTag: "Money / Product360",
    requiredMetrics: ["price", "cost_price", "min_safe_price", "margin_pct"],
  },
  dead_stock: {
    impactTypeLabel: "Заблокированные деньги / возможность",
    trustLabel: "Оценка",
    typicalActionLabel: "Проверить карточку / промо",
    surfaceTag: "Product360 / Checker",
    requiredMetrics: ["stock_qty", "sales_30d", "views_30d"],
  },
  custom: {
    impactTypeLabel: "Настраивается",
    trustLabel: "Настраивается",
    typicalActionLabel: "Выберите на шаге «Действия»",
    surfaceTag: "Настраивается",
  },
};

type CreateProblemResult = {
  definition: ProblemDefinition;
  version: ProblemRuleVersion | null;
  versionError: string | null;
};

type ProblemTemplate = {
  id: string;
  title: string;
  description: string;
  impactSummary: string;
  metricCodes: string[];
  definition: ProblemDefinitionCreatePayload;
  builder: () => RuleBuilderState;
};

type CreateWarningsInput = {
  form: ProblemDefinitionCreatePayload;
  builder: RuleBuilderState;
  selectedMetrics: string[];
};

export type ProblemRuleCreateWizardLogic = {
  defaultDefinitionForm: () => ProblemDefinitionCreatePayload;
  defaultRuleBuilder: (metricCodes: string[]) => RuleBuilderState;
  problemTemplates: (metricCodes: string[]) => ProblemTemplate[];
  buildVersionPayload: (
    builder: RuleBuilderState,
    overrides: Partial<ProblemRuleVersionCreatePayload>,
    allowedActions?: string[],
  ) => ProblemRuleVersionCreatePayload;
  humanizeRulePayload: (
    payload: ProblemRuleVersionCreatePayload,
  ) => HumanRuleFormula;
  collectMetricsFromPayload: (
    payload: ProblemRuleVersionCreatePayload,
  ) => string[];
  buildCreateWarnings: (input: CreateWarningsInput) => string[];
  uniqueProblemCode: (base: string, existingCodes: Set<string>) => string;
  addMetricToBuilder: (
    builder: RuleBuilderState,
    metric: string,
  ) => RuleBuilderState;
  slug: (value: string) => string;
};

export function ProblemRuleCreateWizard({
  open,
  metrics,
  definitions,
  onOpenChange,
  onCreated,
  logic,
  ActionChecklistComponent,
}: {
  open: boolean;
  metrics: MetricCatalogItem[];
  definitions: ProblemDefinition[];
  onOpenChange: (open: boolean) => void;
  onCreated: (
    definition: ProblemDefinition,
    version: ProblemRuleVersion | null,
  ) => void;
  logic: ProblemRuleCreateWizardLogic;
  ActionChecklistComponent: ComponentType<{
    selected: string[];
    disabled?: boolean;
    onChange: (actions: string[]) => void;
  }>;
}) {
  const metricCodes = useMemo(
    () => metrics.map((metric) => metric.metric_code),
    [metrics],
  );
  const templates = useMemo(
    () => logic.problemTemplates(metricCodes),
    [logic, metricCodes],
  );
  const enrichedTemplates = useMemo(
    () =>
      templates.map((template) => {
        const meta = TEMPLATE_METADATA[template.id] ?? {};
        return {
          ...template,
          impactTypeLabel:
            meta.impactTypeLabel ??
            optionText(IMPACT_LABELS, template.definition.impact_type_default),
          trustLabel:
            meta.trustLabel ??
            optionText(TRUST_LABELS, template.definition.trust_state_default),
          typicalActionLabel:
            meta.typicalActionLabel ??
            (template.definition.allowed_actions_json[0] ?? "—"),
          surfaceTag: meta.surfaceTag ?? "Action Center",
          requiredMetrics: meta.requiredMetrics ?? template.metricCodes,
        };
      }),
    [templates],
  );
  const existingCodes = useMemo(
    () => new Set(definitions.map((definition) => definition.problem_code)),
    [definitions],
  );
  const [form, setForm] = useState<ProblemDefinitionCreatePayload>(() =>
    logic.defaultDefinitionForm(),
  );
  const [builder, setBuilder] = useState<RuleBuilderState>(() =>
    logic.defaultRuleBuilder(metricCodes),
  );
  const [selectedTemplateId, setSelectedTemplateId] = useState("custom");
  const [createDraftVersion, setCreateDraftVersion] = useState(true);
  const payload = useMemo(
    () => logic.buildVersionPayload(builder, {}, form.allowed_actions_json),
    [builder, form.allowed_actions_json, logic],
  );
  const humanFormula = useMemo(
    () => logic.humanizeRulePayload(payload),
    [payload, logic],
  );
  const selectedMetrics = useMemo(
    () => logic.collectMetricsFromPayload(payload),
    [payload, logic],
  );
  const selectedTemplate = templates.find(
    (template) => template.id === selectedTemplateId,
  );
  const createWarnings = useMemo(
    () => logic.buildCreateWarnings({ form, builder, selectedMetrics }),
    [form, builder, selectedMetrics, logic],
  );

  useEffect(() => {
    if (!open) return;
    setForm(logic.defaultDefinitionForm());
    setBuilder(logic.defaultRuleBuilder(metricCodes));
    setSelectedTemplateId("custom");
    setCreateDraftVersion(true);
  }, [open, metricCodes, logic]);

  const applyTemplate = (template: ProblemTemplate) => {
    setSelectedTemplateId(template.id);
    setForm({
      ...template.definition,
      problem_code: logic.uniqueProblemCode(
        template.definition.problem_code,
        existingCodes,
      ),
    });
    setBuilder(template.builder());
    setCreateDraftVersion(true);
  };

  const create = useMutation({
    mutationFn: async (): Promise<CreateProblemResult> => {
      const definition = await createProblemDefinition(form);
      if (!createDraftVersion) {
        return { definition, version: null, versionError: null };
      }
      try {
        const version = await createProblemRuleVersion(definition.id, payload);
        return { definition, version, versionError: null };
      } catch (error) {
        return {
          definition,
          version: null,
          versionError:
            error instanceof Error
              ? error.message
              : "Версия правила не создана",
        };
      }
    },
    onSuccess: ({ definition, version, versionError }) => {
      if (versionError) {
        toast.warning(
          `Проблема создана, но черновик правила не создан: ${versionError}`,
        );
      } else {
        toast.success(
          version ? "Проблема и черновик правила созданы" : "Проблема создана",
        );
      }
      setForm(logic.defaultDefinitionForm());
      setBuilder(logic.defaultRuleBuilder(metricCodes));
      onCreated(definition, version);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Создать проблему из сценария</DialogTitle>
          <DialogDescription>
            Выберите сценарий, настройте условие, влияние, доказательства и
            действия. Можно создать сразу проблему и черновик версии правила.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-4">
          <ScenarioTemplatePicker
            templates={enrichedTemplates}
            selectedTemplateId={selectedTemplateId}
            onApplyTemplate={applyTemplate}
          />

          <div className="space-y-4">
            <Alert>
              <CheckCircle2 className="h-4 w-4" />
              <AlertTitle>Что будет создано</AlertTitle>
              <AlertDescription className="text-xs">
                Definition описывает карточку для продавца. Rule version
                описывает формулу: когда проблема появляется, как считается
                влияние и какие доказательства попадут в «Как посчитано?».
              </AlertDescription>
            </Alert>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <InfoTile
                label="2. Бизнес-область"
                value={optionText(CATEGORY_LABELS, form.category)}
              />
              <InfoTile
                label="Тип влияния"
                value={optionText(IMPACT_LABELS, form.impact_type_default)}
              />
              <InfoTile
                label="Доверие"
                value={optionText(TRUST_LABELS, form.trust_state_default)}
              />
            </div>

            {selectedTemplate ? (
              <TemplatePreview
                title="На что влияет"
                value={selectedTemplate.impactSummary}
              />
            ) : null}

            <MetricChipGroups
              metrics={metrics}
              selected={selectedMetrics}
              compact
              onPickMetric={(metric) =>
                setBuilder((current) =>
                  logic.addMetricToBuilder(current, metric),
                )
              }
            />

            <div className="text-xs text-muted-foreground">
              3. Выберите метрики: кликом по метрике добавьте её в условие,
              влияние и доказательства.
            </div>

            <RuleQualityChecklist
              form={form}
              builder={builder}
              selectedMetrics={selectedMetrics}
              createDraftVersion={createDraftVersion}
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Код проблемы">
                <Input
                  value={form.problem_code}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      problem_code: logic.slug(event.target.value),
                    })
                  }
                  placeholder="price_below_safe_margin"
                />
              </Field>
              <Field label="Категория">
                <Select
                  value={form.category}
                  onValueChange={(value) =>
                    setForm({ ...form, category: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORY_OPTIONS.map((item) => (
                      <SelectItem key={item} value={item}>
                        {optionText(CATEGORY_LABELS, item)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Где искать проблему">
                <Select
                  value={form.entity_type}
                  onValueChange={(value) =>
                    setForm({ ...form, entity_type: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ENTITY_OPTIONS.map((item) => (
                      <SelectItem key={item} value={item}>
                        {optionText(ENTITY_LABELS, item)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Серьёзность">
                <Select
                  value={form.severity_default}
                  onValueChange={(value) =>
                    setForm({ ...form, severity_default: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SEVERITY_OPTIONS.map((item) => (
                      <SelectItem key={item} value={item}>
                        {optionText(SEVERITY_LABELS, item)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Доверие">
                <Select
                  value={form.trust_state_default}
                  onValueChange={(value) =>
                    setForm({ ...form, trust_state_default: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TRUST_OPTIONS.map((item) => (
                      <SelectItem key={item} value={item}>
                        {optionText(TRUST_LABELS, item)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Тип влияния">
                <Select
                  value={form.impact_type_default}
                  onValueChange={(value) =>
                    setForm({ ...form, impact_type_default: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {IMPACT_OPTIONS.map((item) => (
                      <SelectItem key={item} value={item}>
                        {optionText(IMPACT_LABELS, item)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Заголовок карточки" className="md:col-span-2">
                <Input
                  value={form.title_template}
                  onChange={(event) =>
                    setForm({ ...form, title_template: event.target.value })
                  }
                  placeholder="Риск низкого остатка для {nm_id}"
                />
              </Field>
              <Field label="Объяснение для продавца" className="md:col-span-2">
                <Textarea
                  rows={3}
                  value={form.description_template}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      description_template: event.target.value,
                    })
                  }
                />
              </Field>
              <Field label="Что делать дальше" className="md:col-span-2">
                <Textarea
                  rows={3}
                  value={form.recommendation_template}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      recommendation_template: event.target.value,
                    })
                  }
                />
              </Field>
            </div>

            <div className="rounded-md border p-3 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-medium">
                    4-5. Условие и формула влияния без JSON
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Соберите правило блоками: метрика, оператор, значение.
                  </div>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={createDraftVersion}
                    onCheckedChange={(checked) =>
                      setCreateDraftVersion(Boolean(checked))
                    }
                  />
                  Создать черновик rule version
                </label>
              </div>

              <VisualFormulaBuilder
                metrics={metrics}
                builder={builder}
                humanFormula={humanFormula}
                onChange={setBuilder}
                conditionTitle="Когда проблема появляется"
                severityTitle="Как ставить серьёзность и доверие"
              />
            </div>

            <EvidenceTemplateEditor
              metrics={metrics}
              builder={builder}
              selectedMetrics={selectedMetrics}
              onChange={setBuilder}
            />

            <ActionChecklistComponent
              selected={form.allowed_actions_json}
              onChange={(allowed_actions_json) =>
                setForm({ ...form, allowed_actions_json })
              }
            />

            {createWarnings.length > 0 ? (
              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Проверьте перед созданием</AlertTitle>
                <AlertDescription>
                  <ul className="list-disc pl-4">
                    {createWarnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            ) : null}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            onClick={() => create.mutate()}
            disabled={
              create.isPending || !form.problem_code || !form.title_template
            }
          >
            {create.isPending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Plus className="mr-1.5 h-4 w-4" />
            )}
            {createDraftVersion
              ? "Создать проблему и черновик правила"
              : "Создать только проблему"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function createWizardPriceSafetyMissing(
  allowedActions: string[],
  selectedMetrics: string[],
): boolean {
  const priceAction = allowedActions.some((action) =>
    [
      "open_price_review",
      "open_promo_planner",
      "review_price",
      "safe_promo",
      "reduce_promo",
      "review_promo",
      "review_promotion",
    ].includes(action),
  );
  return (
    priceAction &&
    !selectedMetrics.some((metric) =>
      ["min_safe_price", "safe_price", "margin_pct", "cost_price", "price_current"].includes(metric),
    )
  );
}

function createWizardPrimarySafeAction(allowedActions: string[]): boolean {
  const aliases: Record<string, string> = {
    bundle: "open_promo_planner",
    check_card_quality: "run_checker",
    content_check: "run_checker",
    cost_review: "upload_cost",
    lower_ads: "open_ads_dashboard",
    pause_ads: "open_ads_dashboard",
    plan_supply: "open_supply_planner",
    pricing_review: "open_price_review",
    reduce_ads: "open_ads_dashboard",
    reduce_promo: "open_promo_planner",
    review_ads: "open_ads_dashboard",
    review_bids: "open_ads_dashboard",
    review_content: "run_checker",
    review_cost: "upload_cost",
    review_price: "open_price_review",
    review_promo: "open_promo_planner",
    safe_promo: "open_promo_planner",
  };
  const primary = new Set([
    "map_sku",
    "open_ads_dashboard",
    "open_data_fix",
    "open_price_review",
    "open_promo_planner",
    "open_supply_planner",
    "run_checker",
    "upload_cost",
  ]);
  return allowedActions.some((action) => primary.has(aliases[action] ?? action));
}

function RuleQualityChecklist({
  form,
  builder,
  selectedMetrics,
  createDraftVersion,
}: {
  form: ProblemDefinitionCreatePayload;
  builder: RuleBuilderState;
  selectedMetrics: string[];
  createDraftVersion: boolean;
}) {
  const hasSellerCopy = Boolean(
    form.title_template.trim() &&
      form.description_template.trim() &&
      form.recommendation_template.trim(),
  );
  const hasCondition = builder.clauses.some(
    (clause) =>
      clause.metric &&
      (clause.operator === "missing" ||
        clause.operator === "present" ||
        clause.value.trim()),
  );
  const evidenceCount = builder.evidenceMetrics.length;
  const hasEvidence = evidenceCount >= 2;
  const hasPriceSafety = !createWizardPriceSafetyMissing(
    form.allowed_actions_json,
    selectedMetrics,
  );
  const hasPrimaryAction = createWizardPrimarySafeAction(
    form.allowed_actions_json,
  );
  const hasRecheck = Boolean(
    builder.recheckHuman.trim() && builder.resolvedMetric.trim(),
  );
  const hasSolveMap = hasPrimaryAction && evidenceCount > 0 && hasRecheck;
  const items = [
    {
      key: "copy",
      ready: hasSellerCopy,
      title: "Карточка для продавца",
      detail: hasSellerCopy
        ? "Есть заголовок, объяснение и следующий шаг."
        : "Заполните заголовок, объяснение и рекомендацию.",
    },
    {
      key: "condition",
      ready: hasCondition,
      title: "Формула обнаружения",
      detail: hasCondition
        ? "Условие проблемы собрано из метрик."
        : "Добавьте хотя бы одно условие с метрикой и значением.",
    },
    {
      key: "evidence",
      ready: hasEvidence,
      title: "Доказательства",
      detail: hasEvidence
        ? `${evidenceCount} метрики попадут в «Как посчитано?».`
        : "Выберите минимум 2 метрики, чтобы продавец видел причину.",
    },
    {
      key: "safety",
      ready: hasPriceSafety && hasPrimaryAction,
      title: "Безопасность действий",
      detail:
        hasPriceSafety && hasPrimaryAction
          ? "Есть основное действие и защитные метрики для рискованных сценариев."
          : "Выберите рабочий экран; для цены/промо нужны cost_price, margin_pct или safe_price.",
    },
    {
      key: "solve_map",
      ready: hasSolveMap,
      title: "Карта решения",
      detail: hasSolveMap
        ? "Шаблон маршрута будет создан для Action Center."
        : "Нужны доказательства, re-check и основное действие.",
    },
    {
      key: "recheck",
      ready: hasRecheck,
      title: "Повторная проверка",
      detail: hasRecheck
        ? "Есть правило, по которому задача закроется или откроется снова."
        : "Опишите re-check и выберите метрику закрытия.",
    },
    {
      key: "draft",
      ready: createDraftVersion,
      title: "Версия правила",
      detail: createDraftVersion
        ? "Черновик версии будет создан сразу."
        : "Будет создана только карточка проблемы без формулы.",
    },
  ];

  const readyCount = items.filter((item) => item.ready).length;

  return (
    <div
      data-testid="problem-rule-quality-checklist"
      className="rounded-md border bg-muted/20 p-3"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium">Карта качества правила</div>
          <div className="text-xs text-muted-foreground">
            Перед созданием проверьте, что новая проблема будет понятна,
            доказуема и безопасна для действия.
          </div>
        </div>
        <Badge variant={readyCount === items.length ? "default" : "outline"}>
          {readyCount}/{items.length} готово
        </Badge>
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        {items.map((item) => (
          <div
            key={item.key}
            className={`min-h-[92px] rounded-md border p-3 ${
              item.ready
                ? "border-success/30 bg-success/[0.05]"
                : "border-warning/35 bg-warning/[0.05]"
            }`}
          >
            <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold">
              {item.ready ? (
                <CheckCircle2 className="h-4 w-4 text-success" />
              ) : (
                <AlertTriangle className="h-4 w-4 text-warning" />
              )}
              {item.title}
            </div>
            <div className="text-xs text-muted-foreground">{item.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
