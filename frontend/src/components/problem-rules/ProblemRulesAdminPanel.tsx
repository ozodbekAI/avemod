// @ts-nocheck
// Admin problem rules professional UI markers:
// Расширенный режим
// JSON только для технических администраторов
// Оценка влияния по типу и доверию
// Карточки продавца
// data-admin-rule-seller-card-preview
// no_backtest, no_evidence, price_safety, too_many_matches, test_only
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Save,
  Search,
} from "lucide-react";
import { toast } from "sonner";

import { useAccounts } from "@/lib/account-context";
import { formatDateTime, formatMoneyCompact } from "@/lib/format";
import {
  archiveProblemRuleVersion,
  backtestProblemRuleVersion,
  createProblemRuleVersion,
  fetchProblemDefinition,
  fetchProblemDefinitions,
  fetchProblemRuleMetrics,
  pauseProblemRuleVersion,
  publishProblemRuleVersion,
  updateProblemDefinition,
  validateProblemRuleVersion,
  type MetricCatalogItem,
  type ProblemDefinition,
  type ProblemDefinitionCreatePayload,
  type ProblemDefinitionDetail,
  type ProblemDefinitionUpdatePayload,
  type ProblemRuleVersion,
  type ProblemRuleVersionCreatePayload,
  type RuleBacktestResponse,
  type RuleValidationResponse,
} from "@/lib/problem-rules";
import type { JsonObject, JsonValue } from "@/lib/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { AdvancedJsonEditor as AdvancedJsonEditorView } from "./AdvancedJsonEditor";
import { BacktestPreview as BacktestPreviewView } from "./BacktestPreview";
import { EvidenceTemplateEditor as EvidenceTemplateEditorView } from "./EvidenceTemplateEditor";
import { MetricChipGroups as MetricChipGroupsView } from "./MetricChipGroups";
import { ProblemRuleCreateWizard as ProblemRuleCreateWizardView } from "./ProblemRuleCreateWizard";
import {
  ProblemRuleDefinitionSummary,
  ProblemRulesList,
} from "./ProblemRulesList";
import { PublishBlockersPanel } from "./PublishBlockersPanel";
import { VisualFormulaBuilder } from "./VisualFormulaBuilder";

type MatchMode = "and" | "or";
type ClauseOperator =
  | ">"
  | ">="
  | "<"
  | "<="
  | "=="
  | "!="
  | "between"
  | "in"
  | "missing"
  | "present";
type NumericOperator =
  | "none"
  | "+"
  | "-"
  | "*"
  | "/"
  | "max"
  | "min"
  | "percent_change";
type NumericTransform = "none" | "abs" | "round";
type OperandKind = "literal" | "metric";
type MetricBusinessArea =
  | "stock"
  | "sales"
  | "price"
  | "cost"
  | "fees_logistics"
  | "ads"
  | "promo"
  | "returns"
  | "content";

type ConditionClause = {
  id: string;
  metric: string;
  operator: ClauseOperator;
  value: string;
  valueTo: string;
};

type NumericBuilderState = {
  metric: string;
  operator: NumericOperator;
  operandKind: OperandKind;
  operandMetric: string;
  operandValue: string;
  transform: NumericTransform;
};

type RuleBuilderState = {
  evaluation_grain: string;
  lookback_days: number;
  dedup_key_template: string;
  matchMode: MatchMode;
  clauses: ConditionClause[];
  impact: NumericBuilderState;
  severityMode: "constant" | "threshold";
  severityConstant: string;
  severityMetric: string;
  severityThreshold: string;
  severityHigh: string;
  severityOtherwise: string;
  confidenceMode: "constant" | "threshold";
  confidenceConstant: string;
  confidenceMetric: string;
  confidenceThreshold: string;
  confidenceHigh: string;
  confidenceOtherwise: string;
  recheckHuman: string;
  resolvedMetric: string;
  resolvedOperator: ClauseOperator;
  resolvedValue: string;
  evidenceFormulaHuman: string;
  evidenceMetrics: string[];
  trustNotes: string;
  moneyCurrency: string;
};

type AdvancedOverrides = Partial<ProblemRuleVersionCreatePayload>;
type ProblemTemplate = {
  id: string;
  title: string;
  description: string;
  impactSummary: string;
  metricCodes: string[];
  definition: ProblemDefinitionCreatePayload;
  builder: () => RuleBuilderState;
};

type PublishIssue = {
  key: string;
  severity: "blocker" | "warning";
  message: string;
};

const CATEGORY_OPTIONS = [
  "profitability",
  "stock",
  "price",
  "ads_promo",
  "ads",
  "promo",
  "data_quality",
  "system",
];
const ENTITY_OPTIONS = [
  "product",
  "account",
  "campaign",
  "warehouse",
  "category",
];
const SEVERITY_OPTIONS = ["critical", "high", "medium", "low"];
const TRUST_OPTIONS = [
  "confirmed",
  "provisional",
  "estimated",
  "opportunity",
  "blocked",
  "test_only",
];
const IMPACT_OPTIONS = [
  "confirmed_loss",
  "probable_loss",
  "blocked_cash",
  "lost_sales_risk",
  "opportunity",
  "data_blocker",
  "system_warning",
];
const ACTION_OPTIONS = [
  "upload_cost",
  "map_sku",
  "open_data_fix",
  "open_price_review",
  "open_promo_planner",
  "open_supply_planner",
  "open_ads_dashboard",
  "run_checker",
  "create_task",
  "recheck",
  "dismiss",
  "review_price",
  "review_cost",
  "review_ads",
  "review_promo",
  "safe_promo",
  "bundle",
  "review_content",
  "plan_supply",
  "reduce_promo",
  "reduce_ads",
  "pause_ads",
  "lower_ads",
  "check_card_quality",
  "review_bids",
];

const CATEGORY_LABELS: Record<string, string> = {
  profitability: "Прибыльность",
  stock: "Остатки",
  price: "Цена",
  ads_promo: "Реклама и промо",
  ads: "Реклама",
  promo: "Промо",
  data_quality: "Качество данных",
  system: "Система",
};

const METRIC_AREA_ORDER: MetricBusinessArea[] = [
  "stock",
  "sales",
  "price",
  "cost",
  "fees_logistics",
  "ads",
  "promo",
  "returns",
  "content",
];

const METRIC_AREA_LABELS: Record<MetricBusinessArea, string> = {
  stock: "Остатки",
  sales: "Продажи",
  price: "Цена",
  cost: "Себестоимость",
  fees_logistics: "Комиссии и логистика",
  ads: "Реклама",
  promo: "Промо",
  returns: "Возвраты",
  content: "Контент",
};

const ENTITY_LABELS: Record<string, string> = {
  product: "Товар",
  account: "Аккаунт",
  campaign: "Кампания",
  warehouse: "Склад",
  category: "Категория",
};

const SEVERITY_LABELS: Record<string, string> = {
  critical: "Критично",
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
};

const TRUST_LABELS: Record<string, string> = {
  confirmed: "Подтверждено",
  provisional: "Предварительно",
  estimated: "Оценка",
  opportunity: "Возможность",
  blocked: "Заблокировано данными",
  test_only: "Только тест",
};

const IMPACT_LABELS: Record<string, string> = {
  confirmed_loss: "Подтверждённая потеря",
  probable_loss: "Вероятная потеря",
  blocked_cash: "Замороженные деньги",
  lost_sales_risk: "Риск потери продаж",
  opportunity: "Возможность роста",
  data_blocker: "Блокер данных",
  system_warning: "Системное предупреждение",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  testing: "Тестируется",
  active: "Активно",
  paused: "На паузе",
  archived: "Архив",
  retired: "Устарело",
};

const ACTION_LABELS: Record<string, string> = {
  upload_cost: "Загрузить себестоимость",
  map_sku: "Сопоставить SKU",
  open_data_fix: "Открыть исправление данных",
  open_price_review: "Открыть пересмотр цены",
  open_promo_planner: "Открыть промо/цену",
  open_supply_planner: "Открыть план поставки",
  open_ads_dashboard: "Открыть рекламу",
  run_checker: "Открыть проверку карточки",
  create_task: "Создать задачу",
  recheck: "Перепроверить",
  dismiss: "Скрыть",
  review_price: "Проверить цену",
  review_cost: "Проверить себестоимость",
  review_ads: "Проверить рекламу",
  review_promo: "Проверить промо",
  safe_promo: "Безопасное промо",
  bundle: "Собрать комплект",
  review_content: "Проверить карточку",
  plan_supply: "Запланировать поставку",
  reduce_promo: "Снизить промо",
  reduce_ads: "Снизить рекламу",
  pause_ads: "Поставить рекламу на паузу",
  lower_ads: "Уменьшить ставки",
  check_card_quality: "Запустить проверку карточки",
  review_bids: "Проверить ставки",
  preview: "Предпросмотр",
};

const GRAIN_LABELS: Record<string, string> = {
  product_period: "Товар за период",
  product_day: "Товар за день",
  account_day: "Аккаунт за день",
  campaign_day: "Кампания за день",
  warehouse_day: "Склад за день",
};

const VALUE_TYPE_LABELS: Record<string, string> = {
  money: "Деньги",
  number: "Число",
  percent: "Процент",
  count: "Количество",
  days: "Дни",
  boolean: "Да/нет",
  text: "Текст",
};

const CLAUSE_OPERATOR_LABELS: Record<string, string> = {
  ">": "больше",
  ">=": "больше или равно",
  "<": "меньше",
  "<=": "меньше или равно",
  "==": "равно",
  "!=": "не равно",
  between: "между",
  in: "в списке",
  missing: "нет данных",
  present: "есть данные",
};

const NUMERIC_OPERATOR_LABELS: Record<string, string> = {
  none: "без операции",
  "+": "плюс",
  "-": "минус",
  "*": "умножить",
  "/": "разделить",
  max: "максимум",
  min: "минимум",
  percent_change: "изменение, %",
};

const TRANSFORM_LABELS: Record<string, string> = {
  none: "как есть",
  abs: "модуль",
  round: "округлить",
};

const TODAY = new Date().toISOString().slice(0, 10);
const DEFAULT_FROM = new Date(Date.now() - 29 * 24 * 60 * 60 * 1000)
  .toISOString()
  .slice(0, 10);
const EMPTY_DEFINITIONS: ProblemDefinition[] = [];
const EMPTY_METRICS: MetricCatalogItem[] = [];
const RULE_CREATION_STEPS = [
  "Выберите сценарий",
  "Выберите бизнес-область",
  "Выберите метрики",
  "Соберите условие",
  "Соберите формулу влияния",
  "Настройте доказательства",
  "Выберите действия для селлера",
  "Настройте правила перепроверки",
  "Запустите тестовый прогон",
  "Проверьте карточки продавца",
  "Опубликуйте правило",
];

export function ProblemRulesAdminPanel() {
  const qc = useQueryClient();
  const { activeId } = useAccounts();
  const [selectedDefinitionId, setSelectedDefinitionId] = useState<
    number | null
  >(null);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(
    null,
  );
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [validation, setValidation] = useState<RuleValidationResponse | null>(
    null,
  );
  const [backtest, setBacktest] = useState<RuleBacktestResponse | null>(null);

  const metricsQuery = useQuery({
    queryKey: ["admin", "problem-rules", "metrics"],
    queryFn: fetchProblemRuleMetrics,
  });
  const definitionsQuery = useQuery({
    queryKey: ["admin", "problem-rules", "definitions"],
    queryFn: fetchProblemDefinitions,
  });
  const detailQuery = useQuery({
    queryKey: ["admin", "problem-rules", "definition", selectedDefinitionId],
    queryFn: () => fetchProblemDefinition(selectedDefinitionId as number),
    enabled: !!selectedDefinitionId,
  });

  const definitions = definitionsQuery.data ?? EMPTY_DEFINITIONS;
  const metrics = metricsQuery.data ?? EMPTY_METRICS;
  const selectedDetail = detailQuery.data ?? null;
  const firstVersionId = selectedDetail?.versions[0]?.id ?? null;
  const selectedVersion =
    selectedDetail?.versions.find(
      (version) => version.id === selectedVersionId,
    ) ??
    selectedDetail?.versions[0] ??
    null;

  useEffect(() => {
    if (selectedDefinitionId || definitions.length === 0) return;
    setSelectedDefinitionId(definitions[0].id);
  }, [definitions, selectedDefinitionId]);

  useEffect(() => {
    setSelectedVersionId(firstVersionId);
    setValidation(null);
    setBacktest(null);
  }, [firstVersionId, selectedDetail?.id]);

  useEffect(() => {
    // Publish backtest to the shared admin-route store so sibling preview
    // surfaces can render from the same sample_issues[0].
    import("./adminRuleBacktestStore").then((m) => {
      m.setAdminRuleBacktest(backtest, selectedVersion?.id ?? null);
    });
  }, [backtest, selectedVersion?.id]);

  const filteredDefinitions = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return definitions;
    return definitions.filter((item) =>
      [item.problem_code, item.category, item.source_module, item.status].some(
        (value) =>
          String(value ?? "")
            .toLowerCase()
            .includes(q),
      ),
    );
  }, [definitions, search]);

  return (
    <div className="space-y-3">
      <AdminRuleWorkflowGuide activeAccountId={activeId} />
      <Tabs defaultValue="catalog">
        <TabsList className="h-auto flex-wrap">
          <TabsTrigger value="catalog">Каталог правил</TabsTrigger>
          <TabsTrigger value="editor">Конструктор</TabsTrigger>
          <TabsTrigger value="performance">Проверка результата</TabsTrigger>
          <TabsTrigger value="metrics">Каталог метрик</TabsTrigger>
        </TabsList>

        <TabsContent value="catalog">
          <div className="grid grid-cols-1 xl:grid-cols-[380px_minmax(0,1fr)] gap-3">
            <ProblemRulesList
              definitions={filteredDefinitions}
              selectedId={selectedDefinitionId}
              loading={definitionsQuery.isLoading}
              search={search}
              onSearch={setSearch}
              onSelect={(id) => setSelectedDefinitionId(id)}
              onCreate={() => setCreateOpen(true)}
            />
            <ProblemRuleDefinitionSummary
              detail={selectedDetail}
              loading={detailQuery.isLoading}
              selectedVersionId={selectedVersionId}
              onSelectVersion={(id) => {
                setSelectedVersionId(id);
                setValidation(null);
                setBacktest(null);
              }}
            />
          </div>
        </TabsContent>

        <TabsContent value="editor">
          <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] gap-3">
            <DefinitionEditor
              detail={selectedDetail}
              disabled={!selectedDetail}
            />
            <RuleVersionWorkspace
              definition={selectedDetail}
              selectedVersion={selectedVersion}
              metrics={metrics}
              activeAccountId={activeId}
              validation={validation}
              backtest={backtest}
              onValidation={setValidation}
              onBacktest={setBacktest}
              onVersionCreated={(version) => {
                setSelectedVersionId(version.id);
                setValidation(null);
                setBacktest(null);
                void qc.invalidateQueries({
                  queryKey: ["admin", "problem-rules"],
                });
              }}
            />
          </div>
        </TabsContent>

        <TabsContent value="performance">
          <RulePerformancePanel
            definitions={definitions}
            detail={selectedDetail}
            selectedVersion={selectedVersion}
            backtest={backtest}
          />
        </TabsContent>

        <TabsContent value="metrics">
          <MetricCatalogPanel
            metrics={metrics}
            loading={metricsQuery.isLoading}
          />
        </TabsContent>
      </Tabs>

      <ProblemRuleCreateWizardView
        open={createOpen}
        metrics={metrics}
        definitions={definitions}
        onOpenChange={setCreateOpen}
        onCreated={(definition, version) => {
          setCreateOpen(false);
          setSelectedDefinitionId(definition.id);
          if (version) setSelectedVersionId(version.id);
          void qc.invalidateQueries({
            queryKey: ["admin", "problem-rules"],
          });
        }}
        ActionChecklistComponent={ActionChecklist}
        logic={{
          defaultDefinitionForm,
          defaultRuleBuilder,
          problemTemplates,
          buildVersionPayload,
          humanizeRulePayload,
          collectMetricsFromPayload,
          buildCreateWarnings,
          uniqueProblemCode,
          addMetricToBuilder,
          slug,
        }}
      />
    </div>
  );
}

function AdminRuleWorkflowGuide({
  activeAccountId,
}: {
  activeAccountId: number | null;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">Динамические проблемы</CardTitle>
            <CardDescription className="text-xs">
              Здесь администратор добавляет новые бизнес-проблемы без деплоя
              кода: правило создаёт задачу, доказательства и действие для
              продавца.
            </CardDescription>
          </div>
          <Badge variant={activeAccountId ? "outline" : "destructive"}>
            {activeAccountId
              ? `Аккаунт #${activeAccountId}`
              : "Аккаунт не выбран"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <AdminRuleStepper activeStep={2} />
      </CardContent>
    </Card>
  );
}

function AdminRuleStepper({ activeStep }: { activeStep: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
      {RULE_CREATION_STEPS.map((step, index) => {
        const active = index === activeStep;
        const done = index < activeStep;
        return (
          <div
            key={step}
            className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${
              active ? "border-primary bg-primary/5" : ""
            }`}
          >
            <Badge variant={done || active ? "default" : "secondary"}>
              {index + 1}
            </Badge>
            <span>{step}</span>
          </div>
        );
      })}
    </div>
  );
}

function DefinitionEditor({
  detail,
  disabled,
}: {
  detail: ProblemDefinitionDetail | null;
  disabled: boolean;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ProblemDefinitionUpdatePayload>({});
  useEffect(() => {
    if (!detail) return;
    setForm({
      source_module: detail.source_module,
      category: detail.category,
      entity_type: detail.entity_type,
      title_template: detail.title_template,
      description_template: detail.description_template,
      recommendation_template: detail.recommendation_template,
      impact_type_default: detail.impact_type_default,
      trust_state_default: detail.trust_state_default,
      severity_default: detail.severity_default,
      allowed_actions_json: detail.allowed_actions_json,
      status: detail.status,
    });
  }, [detail]);

  const update = useMutation({
    mutationFn: () => updateProblemDefinition(detail!.id, form),
    onSuccess: () => {
      toast.success("Описание проблемы сохранено");
      void qc.invalidateQueries({ queryKey: ["admin", "problem-rules"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const locked =
    disabled || !detail || !["draft", "paused"].includes(detail.status);
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">Редактор проблемы</CardTitle>
            <CardDescription className="text-xs">
              {detail?.problem_code ?? "Выберите проблему"}
            </CardDescription>
          </div>
          {detail && <StatusBadge status={detail.status} />}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {!detail ? (
          <div className="text-sm text-muted-foreground">
            Проблема не выбрана.
          </div>
        ) : (
          <>
            {locked && (
              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Редактирование заблокировано</AlertTitle>
                <AlertDescription>
                  Менять можно только проблемы в статусе «Черновик» или «На
                  паузе».
                </AlertDescription>
              </Alert>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Категория">
                <Select
                  value={String(form.category ?? "")}
                  onValueChange={(value) =>
                    setForm({ ...form, category: value })
                  }
                  disabled={locked}
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
                  value={String(form.entity_type ?? "")}
                  onValueChange={(value) =>
                    setForm({ ...form, entity_type: value })
                  }
                  disabled={locked}
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
              <Field label="Серьёзность по умолчанию">
                <Select
                  value={String(form.severity_default ?? "")}
                  onValueChange={(value) =>
                    setForm({ ...form, severity_default: value })
                  }
                  disabled={locked}
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
              <Field label="Доверие по умолчанию">
                <Select
                  value={String(form.trust_state_default ?? "")}
                  onValueChange={(value) =>
                    setForm({ ...form, trust_state_default: value })
                  }
                  disabled={locked}
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
                  value={String(form.impact_type_default ?? "")}
                  onValueChange={(value) =>
                    setForm({ ...form, impact_type_default: value })
                  }
                  disabled={locked}
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
              <Field label="Статус">
                <Select
                  value={String(form.status ?? "")}
                  onValueChange={(value) => setForm({ ...form, status: value })}
                  disabled={locked}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["draft", "testing", "paused", "archived"].map((item) => (
                      <SelectItem key={item} value={item}>
                        {optionText(STATUS_LABELS, item)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Заголовок карточки" className="md:col-span-2">
                <Input
                  disabled={locked}
                  value={String(form.title_template ?? "")}
                  onChange={(event) =>
                    setForm({ ...form, title_template: event.target.value })
                  }
                />
              </Field>
              <Field label="Объяснение для продавца" className="md:col-span-2">
                <Textarea
                  disabled={locked}
                  rows={3}
                  value={String(form.description_template ?? "")}
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
                  disabled={locked}
                  rows={3}
                  value={String(form.recommendation_template ?? "")}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      recommendation_template: event.target.value,
                    })
                  }
                />
              </Field>
            </div>
            <ActionChecklist
              selected={form.allowed_actions_json ?? []}
              disabled={locked}
              onChange={(allowed_actions_json) =>
                setForm({ ...form, allowed_actions_json })
              }
            />
            <Button
              onClick={() => update.mutate()}
              disabled={locked || update.isPending}
            >
              {update.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-1.5 h-4 w-4" />
              )}
              Сохранить описание
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function RuleVersionWorkspace({
  definition,
  selectedVersion,
  metrics,
  activeAccountId,
  validation,
  backtest,
  onValidation,
  onBacktest,
  onVersionCreated,
}: {
  definition: ProblemDefinitionDetail | null;
  selectedVersion: ProblemRuleVersion | null;
  metrics: MetricCatalogItem[];
  activeAccountId: number | null;
  validation: RuleValidationResponse | null;
  backtest: RuleBacktestResponse | null;
  onValidation: (value: RuleValidationResponse | null) => void;
  onBacktest: (value: RuleBacktestResponse | null) => void;
  onVersionCreated: (version: ProblemRuleVersion) => void;
}) {
  const qc = useQueryClient();
  const metricCodes = useMemo(
    () => metrics.map((metric) => metric.metric_code),
    [metrics],
  );
  const [builder, setBuilder] = useState<RuleBuilderState>(() =>
    defaultRuleBuilder(metricCodes),
  );
  const [advancedOverrides, setAdvancedOverrides] = useState<AdvancedOverrides>(
    {},
  );
  const [advancedMode, setAdvancedMode] = useState(false);
  const [advancedError, setAdvancedError] = useState<string | null>(null);
  const [overridePublish, setOverridePublish] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");
  const [sellerPreviewReviewed, setSellerPreviewReviewed] = useState(false);
  const [backtestForm, setBacktestForm] = useState({
    account_id: activeAccountId ? String(activeAccountId) : "",
    date_from: DEFAULT_FROM,
    date_to: TODAY,
    nm_id: "",
    sample_limit: "20",
  });

  useEffect(() => {
    setBuilder(defaultRuleBuilder(metricCodes));
    setAdvancedOverrides({});
    setAdvancedMode(false);
    setAdvancedError(null);
    setSellerPreviewReviewed(false);
  }, [definition?.id, metricCodes]);

  useEffect(() => {
    if (activeAccountId && !backtestForm.account_id) {
      setBacktestForm((current) => ({
        ...current,
        account_id: String(activeAccountId),
      }));
    }
  }, [activeAccountId, backtestForm.account_id]);

  const payload = useMemo(
    () =>
      buildVersionPayload(
        builder,
        advancedOverrides,
        definition.allowed_actions_json,
      ),
    [builder, advancedOverrides, definition.allowed_actions_json],
  );
  const humanFormula = useMemo(() => humanizeRulePayload(payload), [payload]);
  const selectedMetrics = useMemo(
    () => collectMetricsFromPayload(payload),
    [payload],
  );
  const warnings = useMemo(
    () =>
      buildAdminWarnings({
        definition,
        builder,
        payload,
        selectedMetrics,
        validation,
        backtest,
      }),
    [definition, builder, payload, selectedMetrics, validation, backtest],
  );
  const publishBlockers = useMemo(
    () =>
      buildPublishBlockers({
        definition,
        selectedVersion,
        validation,
        backtest,
        builder,
        selectedMetrics,
        override: overridePublish,
        overrideReason,
        sellerPreviewReviewed,
      }),
    [
      definition,
      selectedVersion,
      validation,
      backtest,
      builder,
      selectedMetrics,
      overridePublish,
      overrideReason,
      sellerPreviewReviewed,
    ],
  );

  const createVersion = useMutation({
    mutationFn: () => createProblemRuleVersion(definition!.id, payload),
    onSuccess: (version) => {
      toast.success(`Черновик версии v${version.version} создан`);
      onVersionCreated(version);
      void qc.invalidateQueries({ queryKey: ["admin", "problem-rules"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const validate = useMutation({
    mutationFn: () => {
      if (!selectedVersion)
        throw new Error("Сначала создайте или выберите версию правила");
      return validateProblemRuleVersion(selectedVersion.id, payload);
    },
    onSuccess: (result) => {
      onValidation(result);
      toast[result.valid ? "success" : "error"](
        result.valid ? "Формулы правила валидны" : "В правиле есть ошибки",
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const runBacktest = useMutation({
    mutationFn: () => {
      if (!selectedVersion)
        throw new Error("Сначала создайте или выберите версию правила");
      const accountId = Number(backtestForm.account_id);
      if (!accountId) throw new Error("Выберите аккаунт для тестового прогона");
      return backtestProblemRuleVersion(selectedVersion.id, {
        account_id: accountId,
        date_from: backtestForm.date_from,
        date_to: backtestForm.date_to,
        nm_id: backtestForm.nm_id ? Number(backtestForm.nm_id) : undefined,
        sample_limit: Number(backtestForm.sample_limit || 20),
      });
    },
    onSuccess: (result) => {
      onBacktest(result);
      setSellerPreviewReviewed(false);
      toast.success(`Тестовый прогон: найдено ${result.matched_count} товаров`);
      void qc.invalidateQueries({ queryKey: ["admin", "problem-rules"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const publish = useMutation({
    mutationFn: () => {
      if (!selectedVersion) throw new Error("Сначала выберите версию правила");
      return publishProblemRuleVersion(selectedVersion.id, {
        override: overridePublish,
        override_reason: overridePublish ? overrideReason : null,
      });
    },
    onSuccess: () => {
      toast.success("Правило опубликовано");
      void qc.invalidateQueries({ queryKey: ["admin", "problem-rules"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const pause = useMutation({
    mutationFn: () => pauseProblemRuleVersion(selectedVersion!.id),
    onSuccess: () => {
      toast.success("Правило поставлено на паузу");
      void qc.invalidateQueries({ queryKey: ["admin", "problem-rules"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const archive = useMutation({
    mutationFn: () => archiveProblemRuleVersion(selectedVersion!.id),
    onSuccess: () => {
      toast.success("Правило отправлено в архив");
      void qc.invalidateQueries({ queryKey: ["admin", "problem-rules"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const publishDisabled = publishBlockers.length > 0 || publish.isPending;

  if (!definition) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          Выберите или создайте проблему, затем настройте версию правила.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">
              Конструктор версии правила
            </CardTitle>
            <CardDescription className="text-xs">
              {selectedVersion
                ? `${definition.problem_code} v${selectedVersion.version}`
                : "Сначала создайте черновик версии"}
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {selectedVersion && <StatusBadge status={selectedVersion.status} />}
            {validation && (
              <Badge variant={validation.valid ? "outline" : "destructive"}>
                {validation.valid ? "валидно" : "ошибка"}
              </Badge>
            )}
            {backtest && (
              <Badge variant="outline">
                {backtest.matched_count}/{backtest.evaluated_count} найдено
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Field label="Уровень расчёта">
            <Select
              value={builder.evaluation_grain}
              onValueChange={(value) =>
                setBuilder({ ...builder, evaluation_grain: value })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[
                  "product_period",
                  "product_day",
                  "account_day",
                  "campaign_day",
                  "warehouse_day",
                ].map((item) => (
                  <SelectItem key={item} value={item}>
                    {optionText(GRAIN_LABELS, item)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Период анализа, дней">
            <Input
              type="number"
              min={1}
              max={365}
              value={builder.lookback_days}
              onChange={(event) =>
                setBuilder({
                  ...builder,
                  lookback_days: Number(event.target.value || 30),
                })
              }
            />
          </Field>
          <Field label="Ключ дедупликации">
            <Input
              value={builder.dedup_key_template}
              onChange={(event) =>
                setBuilder({
                  ...builder,
                  dedup_key_template: event.target.value,
                })
              }
            />
          </Field>
        </div>

        <MetricChipGroupsView
          metrics={metrics}
          selected={selectedMetrics}
          onPickMetric={(metric) =>
            setBuilder((current) => addMetricToBuilder(current, metric))
          }
        />

        <VisualFormulaBuilder
          metrics={metrics}
          builder={builder}
          humanFormula={humanFormula}
          onChange={setBuilder}
        />

        <EvidenceTemplateEditorView
          metrics={metrics}
          builder={builder}
          selectedMetrics={selectedMetrics}
          onChange={setBuilder}
        />

        {warnings.length > 0 && (
          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Предупреждения по правилу</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-4">
                {warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        <AdvancedJsonEditorView
          payload={payload}
          advancedOpen={advancedMode}
          onAdvancedOpenChange={setAdvancedMode}
          onApply={(overrides) => {
            setAdvancedOverrides(overrides);
            setAdvancedError(null);
            onValidation(null);
            onBacktest(null);
          }}
          error={advancedError}
          onError={setAdvancedError}
        />

        <div className="flex flex-wrap gap-2">
          <Button
            onClick={() => createVersion.mutate()}
            disabled={createVersion.isPending}
          >
            {createVersion.isPending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-1.5 h-4 w-4" />
            )}
            Создать черновик версии
          </Button>
          <Button
            variant="outline"
            onClick={() => validate.mutate()}
            disabled={!selectedVersion || validate.isPending}
          >
            {validate.isPending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="mr-1.5 h-4 w-4" />
            )}
            Проверить формулы
          </Button>
        </div>

        {validation && !validation.valid ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
            <div className="font-medium">Формула требует исправления</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Проверьте метрики, операторы и отсутствующие данные.
            </div>
          </div>
        ) : null}

        {selectedVersion && selectedMetrics.length === 0 ? (
          <div className="rounded-md border border-dashed p-3 text-sm">
            <div className="font-medium">Метрики не выбраны</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Выберите метрики, на которых будет строиться правило.
            </div>
          </div>
        ) : null}

        <BacktestPreviewView
          selectedVersion={selectedVersion}
          form={backtestForm}
          onFormChange={setBacktestForm}
          backtest={backtest}
          pending={runBacktest.isPending}
          sellerPreviewReviewed={sellerPreviewReviewed}
          onSellerPreviewReviewedChange={setSellerPreviewReviewed}
          onRun={() => runBacktest.mutate()}
        />

        <PublishBlockersPanel
          selectedVersion={selectedVersion}
          validation={validation}
          backtest={backtest}
          blockers={publishBlockers}
          warnings={warnings}
          sellerPreviewReviewed={sellerPreviewReviewed}
          override={overridePublish}
          overrideReason={overrideReason}
          onOverride={setOverridePublish}
          onOverrideReason={setOverrideReason}
          publishDisabled={publishDisabled}
          publishPending={publish.isPending}
          pausePending={pause.isPending}
          archivePending={archive.isPending}
          onPublish={() => publish.mutate()}
          onPause={() => selectedVersion && pause.mutate()}
          onArchive={() => selectedVersion && archive.mutate()}
        />
      </CardContent>
    </Card>
  );
}

function RulePerformancePanel({
  definitions,
  detail,
  selectedVersion,
  backtest,
}: {
  definitions: ProblemDefinition[];
  detail: ProblemDefinitionDetail | null;
  selectedVersion: ProblemRuleVersion | null;
  backtest: RuleBacktestResponse | null;
}) {
  const activeDefinitions = definitions.filter(
    (definition) => definition.status === "active",
  ).length;
  const draftDefinitions = definitions.filter(
    (definition) => definition.status === "draft",
  ).length;
  return (
    <div className="grid grid-cols-1 xl:grid-cols-[420px_minmax(0,1fr)] gap-3">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Состояние каталога правил</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-2">
          <InfoTile label="Проблемы" value={String(definitions.length)} />
          <InfoTile label="Активные" value={String(activeDefinitions)} />
          <InfoTile label="Черновики" value={String(draftDefinitions)} />
          <InfoTile
            label="Архив"
            value={String(
              definitions.filter((item) => item.status === "archived").length,
            )}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            Результат выбранного правила
          </CardTitle>
          <CardDescription className="text-xs">
            {detail?.problem_code ?? "Правило не выбрано"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <InfoTile
              label="Версия"
              value={selectedVersion ? `v${selectedVersion.version}` : "—"}
            />
            <InfoTile
              label="Статус"
              value={
                selectedVersion?.status
                  ? labelFor(STATUS_LABELS, selectedVersion.status)
                  : "—"
              }
            />
            <InfoTile
              label="Найдено"
              value={
                backtest
                  ? `${backtest.matched_count}/${backtest.evaluated_count}`
                  : "—"
              }
            />
            <InfoTile
              label="Влияние"
              value={
                backtest
                  ? formatMoneyCompact(
                      Number(backtest.total_impact_amount ?? 0),
                    )
                  : "—"
              }
            />
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Версия</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Период</TableHead>
                <TableHead>Обновлено</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(detail?.versions ?? []).map((version) => (
                <TableRow key={version.id}>
                  <TableCell className="font-mono text-xs">
                    v{version.version}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={version.status} />
                  </TableCell>
                  <TableCell>{version.lookback_days} дн.</TableCell>
                  <TableCell className="text-xs">
                    {formatDateTime(version.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
              {!detail?.versions?.length && (
                <TableRow>
                  <TableCell
                    colSpan={4}
                    className="py-6 text-center text-muted-foreground"
                  >
                    Версий пока нет.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCatalogPanel({
  metrics,
  loading,
}: {
  metrics: MetricCatalogItem[];
  loading: boolean;
}) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return metrics;
    return metrics.filter((metric) =>
      [
        metric.metric_code,
        metric.title,
        metric.source_module,
        metric.value_type,
      ].some((value) =>
        String(value ?? "")
          .toLowerCase()
          .includes(q),
      ),
    );
  }, [metrics, query]);
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">Каталог метрик</CardTitle>
            <CardDescription className="text-xs">
              Только эти метрики можно использовать в формулах администратора
            </CardDescription>
          </div>
          <div className="relative w-full sm:w-80">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-8"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Поиск метрик"
            />
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="p-6 text-sm text-muted-foreground">
            <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
            Загружаем метрики
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Метрика</TableHead>
                <TableHead>Тип</TableHead>
                <TableHead>Ед.</TableHead>
                <TableHead>Уровень</TableHead>
                <TableHead>Источник</TableHead>
                <TableHead>Доверие</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((metric) => (
                <TableRow key={metric.id}>
                  <TableCell>
                    <div className="font-medium">{metric.metric_code}</div>
                    <div className="text-xs text-muted-foreground">
                      {metric.title}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {labelFor(VALUE_TYPE_LABELS, metric.value_type)}
                    </Badge>
                  </TableCell>
                  <TableCell>{metric.unit ?? "—"}</TableCell>
                  <TableCell>{labelFor(GRAIN_LABELS, metric.grain)}</TableCell>
                  <TableCell>{metric.source_module}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {labelFor(TRUST_LABELS, metric.trust_state)}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function ActionChecklist({
  selected,
  disabled = false,
  onChange,
}: {
  selected: string[];
  disabled?: boolean;
  onChange: (actions: string[]) => void;
}) {
  return (
    <div>
      <Label className="mb-2 block">Разрешённые действия</Label>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {ACTION_OPTIONS.map((action) => (
          <label
            key={action}
            className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm"
          >
            <Checkbox
              disabled={disabled}
              checked={selected.includes(action)}
              onCheckedChange={(checked) => {
                if (checked)
                  onChange(Array.from(new Set([...selected, action])));
                else onChange(selected.filter((item) => item !== action));
              }}
            />
            <span className="truncate">
              {optionText(ACTION_LABELS, action)}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}

function labelFor(labels: Record<string, string>, code: string): string {
  return labels[code] ?? code;
}

function optionText(labels: Record<string, string>, code: string): string {
  const label = labelFor(labels, code);
  return label === code ? code : `${label} (${code})`;
}

function metricBusinessArea(metric: MetricCatalogItem): MetricBusinessArea {
  const text =
    `${metric.metric_code} ${metric.title ?? ""} ${metric.description ?? ""} ${metric.source_module}`.toLowerCase();
  if (/stock|остат|warehouse|days_of_stock|supply/.test(text)) return "stock";
  if (/price|цена|margin|min_safe|safe_price/.test(text)) return "price";
  if (/cost|cogs|supplier|себесто/.test(text)) return "cost";
  if (
    /commission|logistic|storage|fee|tariff|acceptance|комисс|логист/.test(text)
  )
    return "fees_logistics";
  if (/ad_|ads|advert|campaign|cpm|bid|drr|реклам/.test(text)) return "ads";
  if (/promo|discount|скид|промо/.test(text)) return "promo";
  if (/return|refund|возврат/.test(text)) return "returns";
  if (
    /content|photo|title|description|media|card_quality|rating|контент|карточ/.test(
      text,
    )
  )
    return "content";
  if (/sale|sales|order|revenue|qty|avg_daily|выруч|продаж/.test(text))
    return "sales";
  return "sales";
}

function groupMetricsByArea(
  metrics: MetricCatalogItem[],
): Array<{ area: MetricBusinessArea; items: MetricCatalogItem[] }> {
  const groups = new Map<MetricBusinessArea, MetricCatalogItem[]>(
    METRIC_AREA_ORDER.map((area) => [area, []]),
  );
  for (const metric of metrics) {
    groups.get(metricBusinessArea(metric))?.push(metric);
  }
  return METRIC_AREA_ORDER.map((area) => ({
    area,
    items: (groups.get(area) ?? []).sort((a, b) =>
      (a.title || a.metric_code).localeCompare(b.title || b.metric_code, "ru"),
    ),
  }));
}

function addMetricToBuilder(
  builder: RuleBuilderState,
  metric: string,
): RuleBuilderState {
  const clauses = builder.clauses.some((clause) => clause.metric === metric)
    ? builder.clauses
    : [
        ...builder.clauses,
        { id: cryptoId(), metric, operator: ">", value: "0", valueTo: "" },
      ];
  return {
    ...builder,
    clauses,
    evidenceMetrics: Array.from(new Set([...builder.evidenceMetrics, metric])),
  };
}

function StatusBadge({ status }: { status: string }) {
  const variant =
    status === "active"
      ? "default"
      : status === "archived" || status === "retired"
        ? "secondary"
        : "outline";
  return <Badge variant={variant}>{labelFor(STATUS_LABELS, status)}</Badge>;
}

function SeverityBadge({ severity }: { severity: string }) {
  const variant =
    severity === "critical" || severity === "high"
      ? "destructive"
      : severity === "medium"
        ? "secondary"
        : "outline";
  return <Badge variant={variant}>{labelFor(SEVERITY_LABELS, severity)}</Badge>;
}

function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <Label className="mb-1.5 block text-xs">{label}</Label>
      {children}
    </div>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border px-3 py-2">
      <div className="text-[11px] uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 truncate text-sm font-medium">{value}</div>
    </div>
  );
}

function TemplatePreview({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-md border px-3 py-2">
      <div className="text-xs font-medium text-muted-foreground">{title}</div>
      <div className="mt-1 text-sm">{value}</div>
    </div>
  );
}

function defaultDefinitionForm(): ProblemDefinitionCreatePayload {
  return {
    problem_code: "",
    source_module: "problem_engine",
    category: "profitability",
    entity_type: "product",
    title_template: "",
    description_template: "",
    recommendation_template: "",
    impact_type_default: "probable_loss",
    trust_state_default: "provisional",
    severity_default: "medium",
    allowed_actions_json: ["run_checker", "recheck", "dismiss"],
  };
}

function defaultRuleBuilder(metricCodes: string[]): RuleBuilderState {
  const first = metricCodes.includes("stock_qty")
    ? "stock_qty"
    : (metricCodes[0] ?? "stock_qty");
  const second = metricCodes.includes("cost_price")
    ? "cost_price"
    : (metricCodes[1] ?? first);
  return {
    evaluation_grain: "product_period",
    lookback_days: 30,
    dedup_key_template: "{account_id}:{problem_code}:{nm_id}",
    matchMode: "and",
    clauses: [
      { id: cryptoId(), metric: first, operator: ">", value: "0", valueTo: "" },
    ],
    impact: {
      metric: first,
      operator: "none",
      operandKind: "literal",
      operandMetric: second,
      operandValue: "1",
      transform: "none",
    },
    severityMode: "constant",
    severityConstant: "medium",
    severityMetric: first,
    severityThreshold: "100",
    severityHigh: "high",
    severityOtherwise: "medium",
    confidenceMode: "constant",
    confidenceConstant: "estimated",
    confidenceMetric: first,
    confidenceThreshold: "0",
    confidenceHigh: "confirmed",
    confidenceOtherwise: "estimated",
    recheckHuman:
      "Обновить источники метрик и повторно запустить это динамическое правило.",
    resolvedMetric: first,
    resolvedOperator: "<=",
    resolvedValue: "0",
    evidenceFormulaHuman: "",
    evidenceMetrics: [first],
    trustNotes: "",
    moneyCurrency: "RUB",
  };
}

function uniqueProblemCode(base: string, existingCodes: Set<string>): string {
  const safeBase = slug(base || "custom_problem");
  if (!existingCodes.has(safeBase)) return safeBase;
  let index = 2;
  while (existingCodes.has(`${safeBase}_${index}`)) index += 1;
  return `${safeBase}_${index}`;
}

function problemTemplates(metricCodes: string[]): ProblemTemplate[] {
  const metric = (preferred: string, fallback?: string) => {
    if (metricCodes.includes(preferred)) return preferred;
    if (fallback && metricCodes.includes(fallback)) return fallback;
    return metricCodes[0] ?? preferred;
  };
  const clause = (
    metricCode: string,
    operator: ClauseOperator,
    value = "",
    valueTo = "",
  ): ConditionClause => ({
    id: cryptoId(),
    metric: metric(metricCode),
    operator,
    value,
    valueTo,
  });
  const baseBuilder = () => defaultRuleBuilder(metricCodes);
  const withEvidence = (
    builder: RuleBuilderState,
    formula: string,
    evidenceMetrics: string[],
    recheck: string,
  ): RuleBuilderState => ({
    ...builder,
    evidenceFormulaHuman: formula,
    evidenceMetrics: evidenceMetrics.map((code) => metric(code)),
    recheckHuman: recheck,
  });

  return [
    {
      id: "missing_cost_blocks_profit",
      title: "Нет себестоимости, прибыль не считается",
      description: "Есть выручка, но прибыль считать нельзя без cost_price.",
      impactSummary:
        "Влияет на финальную прибыль: negative profit не показывается, пока нет себестоимости.",
      metricCodes: ["cost_price", "revenue_30d"],
      definition: {
        ...defaultDefinitionForm(),
        problem_code: "missing_cost_blocks_profit",
        category: "data_quality",
        entity_type: "product",
        title_template: "Нет себестоимости для {nm_id}",
        description_template:
          "По товару есть выручка, но cost_price отсутствует. Прибыльность нельзя считать финальной.",
        recommendation_template:
          "Загрузите себестоимость или сопоставьте SKU, затем запустите перепроверку.",
        impact_type_default: "data_blocker",
        trust_state_default: "blocked",
        severity_default: "high",
        allowed_actions_json: [
          "upload_cost",
          "map_sku",
          "create_task",
          "recheck",
          "dismiss",
        ],
      },
      builder: () =>
        withEvidence(
          {
            ...baseBuilder(),
            matchMode: "and",
            clauses: [
              clause("cost_price", "missing"),
              clause("revenue_30d", ">", "0"),
            ],
            impact: {
              metric: metric("revenue_30d"),
              operator: "none",
              operandKind: "literal",
              operandMetric: metric("cost_price"),
              operandValue: "1",
              transform: "none",
            },
            confidenceConstant: "blocked",
            resolvedMetric: metric("cost_price"),
            resolvedOperator: "present",
            resolvedValue: "",
          },
          "cost_price отсутствует и revenue_30d больше 0.",
          ["cost_price", "revenue_30d"],
          "После загрузки cost_price правило должно перестать срабатывать.",
        ),
    },
    {
      id: "negative_unit_profit",
      title: "Товар продаётся в минус",
      description: "Unit profit или маржа ниже безопасного уровня.",
      impactSummary:
        "Влияет на probable_loss/confirmed_loss: помогает найти товары, где цена, комиссии, логистика или реклама съедают прибыль.",
      metricCodes: ["unit_profit", "margin_pct", "sales_30d", "cost_price"],
      definition: {
        ...defaultDefinitionForm(),
        problem_code: "negative_unit_profit",
        category: "profitability",
        entity_type: "product",
        title_template: "Отрицательная прибыль по {nm_id}",
        description_template:
          "Unit profit или margin_pct ниже безопасного уровня. Проверяем цену, себестоимость, комиссии, логистику, рекламу и промо.",
        recommendation_template:
          "Проверьте цену, себестоимость, рекламные расходы, промо и логистику. Если данные оценочные, не показывайте это как подтверждённый убыток.",
        impact_type_default: "probable_loss",
        trust_state_default: "provisional",
        severity_default: "high",
        allowed_actions_json: [
          "review_price",
          "review_cost",
          "review_ads",
          "review_promo",
          "create_task",
          "recheck",
          "dismiss",
        ],
      },
      builder: () =>
        withEvidence(
          {
            ...baseBuilder(),
            matchMode: "or",
            clauses: [
              clause("unit_profit", "<", "0"),
              clause("margin_pct", "<", "0.1"),
            ],
            impact: {
              metric: metric("unit_profit"),
              operator: "*",
              operandKind: "metric",
              operandMetric: metric("sales_30d"),
              operandValue: "1",
              transform: "abs",
            },
            severityConstant: "high",
            confidenceConstant: "provisional",
            resolvedMetric: metric("unit_profit"),
            resolvedOperator: ">=",
            resolvedValue: "0",
          },
          "abs(unit_profit * sales_30d), если unit_profit < 0 или margin_pct ниже порога.",
          ["unit_profit", "margin_pct", "sales_30d", "cost_price"],
          "После исправления цены/затрат unit_profit должен стать >= 0.",
        ),
    },
    {
      id: "overstock_slow_moving",
      title: "Много остатка, продажи медленные",
      description: "Остаток высокий, дней запаса много, продажи идут медленно.",
      impactSummary:
        "Влияет на blocked_cash: показывает деньги, замороженные в остатках.",
      metricCodes: [
        "stock_qty",
        "days_of_stock",
        "avg_daily_sales_14d",
        "cost_price",
      ],
      definition: {
        ...defaultDefinitionForm(),
        problem_code: "overstock_slow_moving",
        category: "stock",
        entity_type: "product",
        title_template: "Пересток по {nm_id}",
        description_template:
          "Остаток высокий, days_of_stock большой, а средние продажи низкие. Деньги могут быть заморожены в товаре.",
        recommendation_template:
          "Рассмотрите безопасное промо, проверку цены, комплект, рекламу или качество карточки. Снижение цены допустимо только при безопасной марже.",
        impact_type_default: "blocked_cash",
        trust_state_default: "estimated",
        severity_default: "medium",
        allowed_actions_json: [
          "safe_promo",
          "review_price",
          "bundle",
          "review_content",
          "review_ads",
          "create_task",
          "recheck",
          "dismiss",
        ],
      },
      builder: () =>
        withEvidence(
          {
            ...baseBuilder(),
            matchMode: "and",
            clauses: [
              clause("stock_qty", ">", "50"),
              clause("days_of_stock", ">", "60"),
              clause("avg_daily_sales_14d", "<", "2"),
            ],
            impact: {
              metric: metric("stock_qty"),
              operator: "*",
              operandKind: "metric",
              operandMetric: metric("cost_price"),
              operandValue: "1",
              transform: "round",
            },
            severityConstant: "medium",
            confidenceConstant: "estimated",
            resolvedMetric: metric("days_of_stock"),
            resolvedOperator: "<=",
            resolvedValue: "60",
          },
          "stock_qty > 50 и days_of_stock > 60 и avg_daily_sales_14d < 2.",
          ["stock_qty", "days_of_stock", "avg_daily_sales_14d", "cost_price"],
          "После продаж, поставок или корректировки остатков days_of_stock должен стать <= 60.",
        ),
    },
    {
      id: "low_stock_risk",
      title: "Риск дефицита",
      description: "Запаса мало, а продажи продолжаются.",
      impactSummary:
        "Влияет на lost_sales_risk: показывает риск потерянной выручки при stockout.",
      metricCodes: ["days_of_stock", "avg_daily_sales_7d", "revenue_7d"],
      definition: {
        ...defaultDefinitionForm(),
        problem_code: "low_stock_risk",
        category: "stock",
        entity_type: "product",
        title_template: "Риск низкого остатка по {nm_id}",
        description_template:
          "days_of_stock ниже порога, а продажи за 7 дней идут. Есть риск stockout и потери продаж.",
        recommendation_template:
          "Запланируйте поставку или пополнение. Если поставка невозможна, снизьте промо или рекламу.",
        impact_type_default: "lost_sales_risk",
        trust_state_default: "estimated",
        severity_default: "high",
        allowed_actions_json: [
          "plan_supply",
          "reduce_promo",
          "reduce_ads",
          "create_task",
          "recheck",
          "dismiss",
        ],
      },
      builder: () =>
        withEvidence(
          {
            ...baseBuilder(),
            matchMode: "and",
            clauses: [
              clause("days_of_stock", "<", "7"),
              clause("avg_daily_sales_7d", ">", "1"),
            ],
            impact: {
              metric: metric("revenue_7d"),
              operator: "/",
              operandKind: "literal",
              operandMetric: metric("avg_daily_sales_7d"),
              operandValue: "7",
              transform: "round",
            },
            severityConstant: "high",
            confidenceConstant: "estimated",
            resolvedMetric: metric("days_of_stock"),
            resolvedOperator: ">=",
            resolvedValue: "7",
          },
          "days_of_stock < 7 и avg_daily_sales_7d > 1.",
          ["days_of_stock", "avg_daily_sales_7d", "revenue_7d"],
          "После поставки или падения скорости продаж days_of_stock должен стать >= 7.",
        ),
    },
    {
      id: "ads_spend_without_profit",
      title: "Реклама без прибыли",
      description: "Есть рекламные расходы, но unit profit отрицательный.",
      impactSummary:
        "Влияет на probable_loss: помогает не тратить бюджет на убыточный товар.",
      metricCodes: ["ad_spend_7d", "unit_profit", "sales_30d"],
      definition: {
        ...defaultDefinitionForm(),
        problem_code: "ads_spend_without_profit",
        category: "ads",
        entity_type: "product",
        title_template: "Реклама без прибыли по {nm_id}",
        description_template:
          "Рекламные расходы есть, но unit_profit отрицательный. Реклама может усиливать убыток.",
        recommendation_template:
          "Поставьте рекламу на паузу или снизьте ставки, проверьте карточку, цену и маржинальность.",
        impact_type_default: "probable_loss",
        trust_state_default: "provisional",
        severity_default: "high",
        allowed_actions_json: [
          "pause_ads",
          "lower_ads",
          "check_card_quality",
          "review_bids",
          "review_price",
          "create_task",
          "recheck",
          "dismiss",
        ],
      },
      builder: () =>
        withEvidence(
          {
            ...baseBuilder(),
            matchMode: "and",
            clauses: [
              clause("ad_spend_7d", ">", "1000"),
              clause("unit_profit", "<", "0"),
            ],
            impact: {
              metric: metric("ad_spend_7d"),
              operator: "none",
              operandKind: "literal",
              operandMetric: metric("unit_profit"),
              operandValue: "1",
              transform: "round",
            },
            severityConstant: "high",
            confidenceConstant: "provisional",
            resolvedMetric: metric("unit_profit"),
            resolvedOperator: ">=",
            resolvedValue: "0",
          },
          "ad_spend_7d > 1000 и unit_profit < 0.",
          ["ad_spend_7d", "unit_profit", "sales_30d"],
          "После изменения рекламы или экономики unit_profit должен стать >= 0.",
        ),
    },
    {
      id: "promo_not_profitable",
      title: "Промо без прибыли",
      description:
        "Промо активно, но маржа или unit profit ниже безопасного уровня.",
      impactSummary:
        "Влияет на probable_loss: показывает промо, которое может усиливать убыток вместо роста.",
      metricCodes: [
        "promo_discount_pct",
        "unit_profit",
        "margin_pct",
        "sales_30d",
      ],
      definition: {
        ...defaultDefinitionForm(),
        problem_code: "promo_not_profitable",
        category: "ads_promo",
        entity_type: "product",
        title_template: "Промо без прибыли по {nm_id}",
        description_template:
          "Промо активно, но unit_profit или margin_pct ниже безопасного уровня. Скидка может усиливать убыток.",
        recommendation_template:
          "Проверьте безопасную цену и маржу. Снижать цену или усиливать промо нельзя без подтверждённой экономики.",
        impact_type_default: "probable_loss",
        trust_state_default: "provisional",
        severity_default: "high",
        allowed_actions_json: [
          "review_promo",
          "safe_promo",
          "review_price",
          "review_cost",
          "create_task",
          "recheck",
          "dismiss",
        ],
      },
      builder: () =>
        withEvidence(
          {
            ...baseBuilder(),
            matchMode: "and",
            clauses: [
              clause("promo_discount_pct", ">", "0"),
              clause("unit_profit", "<", "0"),
            ],
            impact: {
              metric: metric("unit_profit"),
              operator: "*",
              operandKind: "metric",
              operandMetric: metric("sales_30d"),
              operandValue: "1",
              transform: "abs",
            },
            severityConstant: "high",
            confidenceConstant: "provisional",
            resolvedMetric: metric("unit_profit"),
            resolvedOperator: ">=",
            resolvedValue: "0",
          },
          "promo_discount_pct > 0 и unit_profit < 0. Перед промо нужна проверка безопасной маржи.",
          ["promo_discount_pct", "unit_profit", "margin_pct", "sales_30d"],
          "После изменения промо или цены unit_profit должен стать >= 0.",
        ),
    },
    {
      id: "price_below_safe_margin",
      title: "Цена ниже безопасной маржи",
      description: "Маржа ниже безопасного порога, снижение цены опасно.",
      impactSummary:
        "Влияет на safety warning: блокирует опасные price/promo рекомендации.",
      metricCodes: ["price_current", "margin_pct", "cost_price"],
      definition: {
        ...defaultDefinitionForm(),
        problem_code: "price_below_safe_margin",
        category: "price",
        entity_type: "product",
        title_template: "Цена ниже безопасной маржи по {nm_id}",
        description_template:
          "Текущая цена ниже безопасного уровня или маржа ниже целевого порога.",
        recommendation_template:
          "Проверьте safe price range и рассчитайте цену, которая сохраняет целевую маржу.",
        impact_type_default: "system_warning",
        trust_state_default: "estimated",
        severity_default: "high",
        allowed_actions_json: [
          "review_price",
          "review_cost",
          "create_task",
          "recheck",
          "dismiss",
        ],
      },
      builder: () =>
        withEvidence(
          {
            ...baseBuilder(),
            matchMode: "and",
            clauses: [
              clause("cost_price", "present"),
              clause("margin_pct", "<", "0.1"),
            ],
            impact: {
              metric: metric("price_current"),
              operator: "none",
              operandKind: "literal",
              operandMetric: metric("cost_price"),
              operandValue: "1",
              transform: "none",
            },
            severityConstant: "high",
            confidenceConstant: "estimated",
            resolvedMetric: metric("margin_pct"),
            resolvedOperator: ">=",
            resolvedValue: "0.1",
          },
          "cost_price есть и margin_pct < 10%. Снижение цены нельзя рекомендовать без проверки safe price range.",
          ["price_current", "margin_pct", "cost_price"],
          "После пересмотра цены margin_pct должен быть >= 10%.",
        ),
    },
    {
      id: "dead_stock",
      title: "Мёртвый остаток",
      description: "Остаток есть, но продаж за период нет.",
      impactSummary:
        "Влияет на blocked_cash: показывает товары, где деньги лежат в остатке без движения.",
      metricCodes: ["stock_qty", "sales_30d", "days_of_stock", "cost_price"],
      definition: {
        ...defaultDefinitionForm(),
        problem_code: "dead_stock",
        category: "stock",
        entity_type: "product",
        title_template: "Мёртвый остаток по {nm_id}",
        description_template:
          "По товару есть остаток, но продаж за 30 дней нет. Деньги могут быть заморожены в товаре.",
        recommendation_template:
          "Проверьте карточку, цену и доступность товара. Рассмотрите безопасное промо или комплект только после проверки маржи.",
        impact_type_default: "blocked_cash",
        trust_state_default: "estimated",
        severity_default: "medium",
        allowed_actions_json: [
          "review_content",
          "review_price",
          "safe_promo",
          "bundle",
          "create_task",
          "recheck",
          "dismiss",
        ],
      },
      builder: () =>
        withEvidence(
          {
            ...baseBuilder(),
            matchMode: "and",
            clauses: [
              clause("stock_qty", ">", "0"),
              clause("sales_30d", "==", "0"),
            ],
            impact: {
              metric: metric("stock_qty"),
              operator: "*",
              operandKind: "metric",
              operandMetric: metric("cost_price"),
              operandValue: "1",
              transform: "round",
            },
            severityConstant: "medium",
            confidenceConstant: "estimated",
            resolvedMetric: metric("sales_30d"),
            resolvedOperator: ">",
            resolvedValue: "0",
          },
          "stock_qty > 0 и sales_30d = 0. Влияние оценивается как stock_qty * cost_price.",
          ["stock_qty", "sales_30d", "days_of_stock", "cost_price"],
          "После продаж или корректировки остатков sales_30d должен стать > 0.",
        ),
    },
    {
      id: "fast_stock_depletion",
      title: "Быстро заканчивается остаток",
      description:
        "Остаток заканчивается быстрее обычного при активных продажах.",
      impactSummary:
        "Влияет на lost_sales_risk: показывает риск потерять продажи из-за скорого stockout.",
      metricCodes: [
        "days_of_stock",
        "avg_daily_sales_7d",
        "stock_qty",
        "revenue_7d",
      ],
      definition: {
        ...defaultDefinitionForm(),
        problem_code: "fast_stock_depletion",
        category: "stock",
        entity_type: "product",
        title_template: "Быстро заканчивается остаток по {nm_id}",
        description_template:
          "days_of_stock очень низкий, а средние продажи за 7 дней сохраняются. Есть риск быстро уйти в ноль по остатку.",
        recommendation_template:
          "Запланируйте поставку или перераспределение остатка. Если поставка невозможна, осторожно снизьте промо или рекламу.",
        impact_type_default: "lost_sales_risk",
        trust_state_default: "estimated",
        severity_default: "high",
        allowed_actions_json: [
          "plan_supply",
          "reduce_promo",
          "reduce_ads",
          "create_task",
          "recheck",
          "dismiss",
        ],
      },
      builder: () =>
        withEvidence(
          {
            ...baseBuilder(),
            matchMode: "and",
            clauses: [
              clause("days_of_stock", "<", "3"),
              clause("avg_daily_sales_7d", ">", "1"),
            ],
            impact: {
              metric: metric("revenue_7d"),
              operator: "/",
              operandKind: "literal",
              operandMetric: metric("avg_daily_sales_7d"),
              operandValue: "7",
              transform: "round",
            },
            severityConstant: "high",
            confidenceConstant: "estimated",
            resolvedMetric: metric("days_of_stock"),
            resolvedOperator: ">=",
            resolvedValue: "3",
          },
          "days_of_stock < 3 и avg_daily_sales_7d > 1.",
          ["days_of_stock", "avg_daily_sales_7d", "stock_qty", "revenue_7d"],
          "После поставки или замедления продаж days_of_stock должен стать >= 3.",
        ),
    },
    {
      id: "custom",
      title: "Свой сценарий",
      description: "Начать с пустого правила и собрать формулу из блоков.",
      impactSummary:
        "Вы сами выбираете тип влияния: потеря, риск, opportunity, data blocker или system warning.",
      metricCodes: [],
      definition: defaultDefinitionForm(),
      builder: baseBuilder,
    },
  ];
}

const ACTION_ALIASES: Record<string, string> = {
  ads_review: "open_ads_dashboard",
  bundle: "open_promo_planner",
  check_card_quality: "run_checker",
  content_check: "run_checker",
  cost_review: "upload_cost",
  lower_ads: "open_ads_dashboard",
  open_costs: "upload_cost",
  pause_ads: "open_ads_dashboard",
  plan_supply: "open_supply_planner",
  price_review: "open_price_review",
  pricing_review: "open_price_review",
  promo_planner: "open_promo_planner",
  reduce_ads: "open_ads_dashboard",
  reduce_promo: "open_promo_planner",
  review_ads: "open_ads_dashboard",
  review_bids: "open_ads_dashboard",
  review_content: "run_checker",
  review_cost: "upload_cost",
  review_price: "open_price_review",
  review_promo: "open_promo_planner",
  review_promotion: "open_promo_planner",
  safe_promo: "open_promo_planner",
  supply_review: "open_supply_planner",
};

const PRIMARY_SAFE_ACTIONS = new Set([
  "classify_expense",
  "map_sku",
  "open_ads_dashboard",
  "open_data_fix",
  "open_price_review",
  "open_promo_planner",
  "open_supply_planner",
  "run_checker",
  "upload_cost",
]);

const NON_PRIMARY_ACTIONS = new Set([
  "assign",
  "create_task",
  "dismiss",
  "open_product",
  "open_results",
  "recheck",
]);

function normalizeAllowedActions(actions: string[] = []): string[] {
  const normalized: string[] = [];
  for (const action of actions) {
    const code = ACTION_ALIASES[action] ?? action;
    if (!code || normalized.includes(code)) continue;
    normalized.push(code);
  }
  return normalized;
}

function firstPrimarySafeAction(actions: string[] = []): string | null {
  return (
    normalizeAllowedActions(actions).find((action) =>
      PRIMARY_SAFE_ACTIONS.has(action),
    ) ?? null
  );
}

function buildSolveMapTemplate(
  builder: RuleBuilderState,
  allowedActions: string[],
): JsonObject {
  const normalized = normalizeAllowedActions(allowedActions);
  const primaryAction =
    firstPrimarySafeAction(allowedActions) ??
    normalized.find((action) => !NON_PRIMARY_ACTIONS.has(action)) ??
    "create_task";
  const metrics = Array.from(
    new Set(
      [
        ...builder.evidenceMetrics,
        builder.clauses[0]?.metric,
        builder.impact.metric,
        builder.resolvedMetric,
      ].filter((metric): metric is string => Boolean(metric?.trim())),
    ),
  );
  const requiredMetrics = metrics.length ? metrics : ["source_metric"];
  const primaryReady = PRIMARY_SAFE_ACTIONS.has(primaryAction);
  return {
    title: `Карта решения: ${labelFor(ACTION_LABELS, primaryAction)}`,
    summary:
      "Проверьте доказательства, откройте рабочий экран для действия и запустите перепроверку результата.",
    steps: [
      {
        step_id: "evidence",
        order: 1,
        title: "Проверить доказательства",
        description:
          "Откройте «Как посчитано?» и проверьте формулу, факты, источники и свежесть данных.",
        status: "ready",
        action_code: null,
        target_href: null,
        required_metrics: requiredMetrics,
        blocking_reason: null,
        completion_signal: "Доказательства и источники понятны.",
      },
      {
        step_id: "primary_action",
        order: 2,
        title: labelFor(ACTION_LABELS, primaryAction),
        description:
          "Перейдите в точный рабочий экран, где продавец сможет выполнить следующий шаг по этой проблеме.",
        status: primaryReady ? "available" : "blocked",
        action_code: primaryAction,
        target_href: null,
        required_metrics: requiredMetrics,
        blocking_reason: primaryReady
          ? null
          : "Выберите основное безопасное действие.",
        completion_signal:
          "Основное действие выполнено или передано владельцу.",
      },
      {
        step_id: "recheck",
        order: 3,
        title: "Перепроверить результат",
        description:
          "После действия запустите повторную проверку по правилу закрытия.",
        status: "available",
        action_code: "recheck",
        target_href: null,
        required_metrics: requiredMetrics,
        blocking_reason: null,
        completion_signal: "Правило пересчитано после действия.",
      },
    ],
  };
}

function buildVersionPayload(
  builder: RuleBuilderState,
  overrides: AdvancedOverrides,
  allowedActions: string[] = [],
): ProblemRuleVersionCreatePayload {
  const generated: ProblemRuleVersionCreatePayload = {
    evaluation_grain: builder.evaluation_grain,
    lookback_days: builder.lookback_days,
    condition_json: buildConditionJson(builder.matchMode, builder.clauses),
    impact_formula_json: buildNumericJson(builder.impact),
    severity_formula_json: buildSeverityFormula(builder),
    confidence_formula_json: buildConfidenceFormula(builder),
    dedup_key_template: builder.dedup_key_template,
    recheck_rule_json: {
      human: builder.recheckHuman,
      resolved_when: buildSingleClauseJson({
        id: "resolved",
        metric: builder.resolvedMetric,
        operator: builder.resolvedOperator,
        value: builder.resolvedValue,
        valueTo: "",
      }),
    },
    evidence_template_json: {
      formula_human:
        builder.evidenceFormulaHuman ||
        humanizeCondition(
          buildConditionJson(builder.matchMode, builder.clauses),
        ),
      recheck_rule_human: builder.recheckHuman,
      money_currency: builder.moneyCurrency,
      selected_input_metrics: builder.evidenceMetrics,
      trust_notes: builder.trustNotes
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      solve_map_template: buildSolveMapTemplate(builder, allowedActions),
    },
  };
  return { ...generated, ...overrides };
}

function buildConditionJson(
  mode: MatchMode,
  clauses: ConditionClause[],
): JsonValue {
  const parts = clauses
    .map(buildSingleClauseJson)
    .filter(Boolean) as JsonValue[];
  if (parts.length === 0) return {};
  if (parts.length === 1) return parts[0];
  return { [mode]: parts };
}

function buildSingleClauseJson(clause: ConditionClause): JsonValue {
  const metric = { metric: clause.metric };
  if (clause.operator === "missing") return { missing: [clause.metric] };
  if (clause.operator === "present")
    return { not: { missing: [clause.metric] } };
  if (clause.operator === "between")
    return {
      between: [
        metric,
        parseLiteral(clause.value),
        parseLiteral(clause.valueTo),
      ],
    };
  if (clause.operator === "in")
    return {
      in: [
        metric,
        clause.value.split(",").map((item) => parseLiteral(item.trim())),
      ],
    };
  return { [clause.operator]: [metric, parseLiteral(clause.value)] };
}

function buildNumericJson(state: NumericBuilderState): JsonValue {
  let expression: JsonValue = { metric: state.metric };
  if (state.operator !== "none") {
    const operand =
      state.operandKind === "metric"
        ? { metric: state.operandMetric }
        : parseLiteral(state.operandValue);
    expression =
      state.operator === "percent_change"
        ? { percent_change: [expression, operand] }
        : { [state.operator]: [expression, operand] };
  }
  if (state.transform === "abs") expression = { abs: expression };
  if (state.transform === "round") expression = { round: [expression, 2] };
  return expression;
}

function buildSeverityFormula(builder: RuleBuilderState): JsonValue {
  if (builder.severityMode === "constant") return builder.severityConstant;
  return {
    case: [
      {
        if: {
          ">": [
            { metric: builder.severityMetric },
            parseLiteral(builder.severityThreshold),
          ],
        },
        then: builder.severityHigh,
      },
      { else: builder.severityOtherwise },
    ],
  };
}

function buildConfidenceFormula(builder: RuleBuilderState): JsonValue {
  if (builder.confidenceMode === "constant") return builder.confidenceConstant;
  return {
    case: [
      {
        if: {
          ">": [
            { metric: builder.confidenceMetric },
            parseLiteral(builder.confidenceThreshold),
          ],
        },
        then: builder.confidenceHigh,
      },
      { else: builder.confidenceOtherwise },
    ],
  };
}

function humanizeRulePayload(payload: ProblemRuleVersionCreatePayload) {
  return {
    condition: humanizeCondition(payload.condition_json),
    impact: humanizeCondition(payload.impact_formula_json),
    severity: humanizeCondition(payload.severity_formula_json),
    confidence: humanizeCondition(payload.confidence_formula_json),
  };
}

function humanizeCondition(expression: JsonValue): string {
  if (expression === null || expression === undefined) return "";
  if (typeof expression !== "object") return String(expression);
  if (Array.isArray(expression))
    return expression.map(humanizeCondition).join(", ");
  const entries = Object.entries(expression);
  if (entries.length !== 1) return JSON.stringify(expression);
  const [op, raw] = entries[0];
  if (op === "metric") return String(raw);
  if (op === "missing" && Array.isArray(raw))
    return `${raw.join(", ")} отсутствует`;
  if (op === "not") return `НЕ (${humanizeCondition(raw as JsonValue)})`;
  if ((op === "and" || op === "or") && Array.isArray(raw)) {
    return raw
      .map((item) => `(${humanizeCondition(item as JsonValue)})`)
      .join(op === "and" ? " И " : " ИЛИ ");
  }
  if (op === "case") return "УСЛОВИЕ " + JSON.stringify(raw);
  if (Array.isArray(raw))
    return raw
      .map((item) => humanizeCondition(item as JsonValue))
      .join(` ${labelFor(CLAUSE_OPERATOR_LABELS, op)} `);
  return `${op}(${humanizeCondition(raw as JsonValue)})`;
}

function collectMetricsFromPayload(
  payload: ProblemRuleVersionCreatePayload,
): string[] {
  const codes = new Set<string>();
  for (const expression of [
    payload.condition_json,
    payload.impact_formula_json,
    payload.severity_formula_json,
    payload.confidence_formula_json,
    payload.recheck_rule_json,
    payload.evidence_template_json,
  ]) {
    collectMetrics(expression, codes);
  }
  return Array.from(codes).sort();
}

function collectMetrics(node: unknown, codes: Set<string>) {
  if (!node || typeof node !== "object") return;
  if (Array.isArray(node)) {
    node.forEach((item) => collectMetrics(item, codes));
    return;
  }
  const obj = node as Record<string, unknown>;
  if (Object.keys(obj).length === 1 && typeof obj.metric === "string") {
    codes.add(obj.metric);
    return;
  }
  if (Array.isArray(obj.missing)) {
    obj.missing.forEach((item) => {
      if (typeof item === "string") codes.add(item);
      else collectMetrics(item, codes);
    });
  }
  Object.values(obj).forEach((value) => collectMetrics(value, codes));
}

function buildAdminWarnings({
  definition,
  builder,
  payload,
  selectedMetrics,
  validation,
  backtest,
}: {
  definition: ProblemDefinitionDetail | null;
  builder: RuleBuilderState;
  payload: ProblemRuleVersionCreatePayload;
  selectedMetrics: string[];
  validation: RuleValidationResponse | null;
  backtest: RuleBacktestResponse | null;
}) {
  const warnings: string[] = [];
  if (!builder.evidenceMetrics.length)
    warnings.push(
      "Не выбраны поля доказательств. Продавец не поймёт, откуда взялась проблема.",
    );
  if (!definition || definition.status !== "active")
    warnings.push(
      "Правило остаётся тестовым для продавца, пока версия не опубликована.",
    );
  if (priceSafetyMissing(definition, selectedMetrics)) {
    warnings.push(
      "Есть действие по цене/промо, но в формуле нет метрик безопасности маржи или себестоимости.",
    );
  }
  if (!firstPrimarySafeAction(definition?.allowed_actions_json ?? [])) {
    warnings.push(
      "Выберите хотя бы одно основное безопасное действие: рабочий экран, загрузку данных, рекламу, поставки, цену/промо или проверку карточки.",
    );
  }
  if (validation && !validation.valid)
    warnings.push("Валидация формулы не пройдена.");
  if (backtest && backtest.evaluated_count > 0) {
    const ratio = backtest.matched_count / backtest.evaluated_count;
    if (backtest.evaluated_count >= 20 && ratio > 0.5)
      warnings.push(
        "Правило срабатывает больше чем на половину проверенных товаров.",
      );
    for (const [metric, count] of Object.entries(
      backtest.missing_metric_stats,
    )) {
      if (count / backtest.evaluated_count > 0.2)
        warnings.push(
          `Метрика ${metric} отсутствует более чем у 20% проверенных товаров.`,
        );
    }
    const estimated = backtest.sample_issues.filter((issue) =>
      ["estimated", "provisional", "opportunity"].includes(
        String(issue.trust_state ?? ""),
      ),
    ).length;
    if (
      backtest.sample_issues.length &&
      estimated / backtest.sample_issues.length > 0.6
    )
      warnings.push(
        "Большая часть примеров основана на оценочных или предварительных данных.",
      );
  }
  const evidence = payload.evidence_template_json as JsonObject;
  if (!String(evidence.formula_human ?? "").trim())
    warnings.push(
      "Не заполнена формула простыми словами для окна «Как посчитано?».",
    );
  if (!hasSolveMapTemplate(evidence.solve_map_template)) {
    warnings.push(
      "Нет шаблона «Карта решения»: продавец не увидит точный маршрут действия.",
    );
  }
  return Array.from(new Set(warnings));
}

function priceSafetyMissingForActions(
  allowedActions: string[],
  selectedMetrics: string[],
): boolean {
  const priceAction = normalizeAllowedActions(allowedActions).some((action) =>
    ["open_price_review", "open_promo_planner"].includes(action),
  );
  return (
    priceAction &&
    !selectedMetrics.some((metric) =>
      [
        "min_safe_price",
        "safe_price",
        "margin_pct",
        "cost_price",
        "price_current",
      ].includes(metric),
    )
  );
}

function priceSafetyMissing(
  definition: ProblemDefinitionDetail | null,
  selectedMetrics: string[],
): boolean {
  return priceSafetyMissingForActions(
    definition?.allowed_actions_json ?? [],
    selectedMetrics,
  );
}

function hasSolveMapTemplate(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const template = value as Record<string, unknown>;
  return (
    Boolean(String(template.title ?? "").trim()) &&
    Boolean(String(template.summary ?? "").trim()) &&
    Array.isArray(template.steps) &&
    template.steps.length > 0
  );
}

function hasCondition(value: unknown): boolean {
  return Boolean(
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.keys(value).length > 0,
  );
}

function buildCreateWarnings({
  form,
  builder,
  selectedMetrics,
}: {
  form: ProblemDefinitionCreatePayload;
  builder: RuleBuilderState;
  selectedMetrics: string[];
}): string[] {
  const warnings: string[] = [];
  if (!builder.evidenceMetrics.length)
    warnings.push(
      "Не выбраны поля доказательств для «Как посчитано?». Лучше выбрать хотя бы 2-3 ключевые метрики.",
    );
  if (priceSafetyMissingForActions(form.allowed_actions_json, selectedMetrics))
    warnings.push(
      "В сценарии есть цена или промо, но не выбраны метрики безопасной маржи: cost_price, margin_pct или safe_price.",
    );
  if (!firstPrimarySafeAction(form.allowed_actions_json))
    warnings.push(
      "Выберите основное безопасное действие: рабочий экран, загрузку данных, поставку, рекламу, цену/промо или проверку карточки.",
    );
  if (
    ["estimated", "provisional", "opportunity"].includes(
      form.trust_state_default,
    )
  )
    warnings.push(
      "Влияние будет предварительным или оценочным. Не называйте его сохранёнными деньгами без результата после действия.",
    );
  warnings.push(
    "Новое правило остаётся тестовым для продавца, пока версия не опубликована.",
  );
  if (
    !form.title_template.trim() ||
    !form.description_template.trim() ||
    !form.recommendation_template.trim()
  )
    warnings.push(
      "Заполните заголовок, объяснение и следующий шаг для продавца.",
    );
  return Array.from(new Set(warnings));
}

export function buildPublishBlockers({
  definition,
  selectedVersion,
  validation,
  backtest,
  builder,
  selectedMetrics,
  override,
  overrideReason,
  sellerPreviewReviewed,
}: {
  definition: ProblemDefinitionDetail | null;
  selectedVersion: ProblemRuleVersion | null;
  validation: RuleValidationResponse | null;
  backtest: RuleBacktestResponse | null;
  builder: RuleBuilderState;
  selectedMetrics: string[];
  override: boolean;
  overrideReason: string;
  sellerPreviewReviewed: boolean;
}): PublishIssue[] {
  const blockers: PublishIssue[] = [];
  if (!selectedVersion) {
    blockers.push({
      key: "no_version",
      severity: "blocker",
      message: "Сначала создайте или выберите версию правила.",
      why: "Без версии нечего публиковать.",
      fix: "Создайте черновик версии на шаге 4.",
    });
  } else if (!hasCondition(selectedVersion.condition_json)) {
    blockers.push({
      key: "no_condition",
      severity: "blocker",
      message: "Добавьте условие обнаружения проблемы.",
      why: "Без условия правило не сможет ничего найти.",
      fix: "Заполните условие на шаге «Условие».",
    });
  }
  if (!validation) {
    blockers.push({
      key: "no_validation",
      severity: "blocker",
      message: "Сначала нажмите «Проверить формулы».",
      why: "Проверка формул гарантирует, что метрики и операторы известны.",
      fix: "Нажмите кнопку «Проверить формулы».",
    });
  } else if (!validation.valid) {
    blockers.push({
      key: "invalid_formula",
      severity: "blocker",
      message: "Формула требует исправления.",
      why: "Валидация формулы не пройдена, правило не сможет посчитать влияние.",
      fix: "Откройте шаг «Расчёт влияния» и исправьте ошибки.",
    });
  }
  if (validation && Array.isArray(validation.required_metrics)) {
    const unknown = validation.required_metrics.filter(
      (m) => !selectedMetrics.includes(m),
    );
    if (unknown.length > 0) {
      blockers.push({
        key: "unknown_metric_or_operator",
        severity: "blocker",
        message: `Формула ссылается на метрики, которых нет в каталоге: ${unknown.join(", ")}.`,
        why: "Неизвестная метрика или оператор приведёт к ошибке во время расчёта.",
        fix: "Уберите неизвестные метрики или добавьте их в каталог.",
      });
    }
  }
  if (!builder.evidenceMetrics.length) {
    blockers.push({
      key: "no_evidence",
      severity: "blocker",
      message: "Выберите поля доказательств для окна «Как посчитано?».",
      why: "Без доказательств продавец не поймёт, откуда взялась проблема.",
      fix: "На шаге «Доказательства» отметьте 2-3 ключевые метрики.",
    });
  }
  if (!backtest) {
    blockers.push({
      key: "no_backtest",
      severity: "blocker",
      message:
        "Сначала запустите тестовый прогон: предпросмотр влияния обязателен перед публикацией.",
      why: "Без backtest нельзя оценить охват и влияние правила.",
      fix: "Запустите backtest на шаге 9.",
    });
  } else if (backtest.sample_issues.length === 0) {
    blockers.push({
      key: "seller_preview_missing",
      severity: "blocker",
      message:
        "Тестовый прогон должен показать хотя бы одну карточку-пример для предпросмотра.",
      why: "Без sample-карточки не видно, как проблема выглядит для продавца.",
      fix: "Расширьте условие или подберите другой период backtest.",
    });
  }
  if (!sellerPreviewReviewed) {
    blockers.push({
      key: "seller_preview_missing",
      severity: "blocker",
      message:
        "Проверьте карточки продавца и подтвердите предпросмотр перед публикацией.",
      why: "Админ должен глазами проверить, как правило выглядит на всех поверхностях.",
      fix: "Отметьте чекбокс «Я проверил(а) карточки продавца».",
    });
  }
  if (
    !definition?.title_template?.trim() ||
    !definition?.description_template?.trim() ||
    !definition?.recommendation_template?.trim()
  ) {
    blockers.push({
      key: "seller_copy",
      severity: "blocker",
      message:
        "Заполните заголовок, объяснение и точный следующий шаг для продавца.",
      why: "Без текста для продавца проблема бесполезна.",
      fix: "Заполните тексты на шаге «Описание проблемы».",
    });
  }
  const evidenceTemplate = selectedVersion?.evidence_template_json as
    | JsonObject
    | undefined;
  if (
    !hasSolveMapTemplate(
      evidenceTemplate?.solve_map_template ?? evidenceTemplate?.solve_map,
    )
  ) {
    blockers.push({
      key: "solve_map",
      severity: "blocker",
      message: "Добавьте шаблон «Карта решения» с точным рабочим экраном.",
      why: "Продавец должен видеть точный маршрут действия.",
      fix: "На шаге «Действия» опишите шаги карты решения.",
    });
  }
  // Dangerous action whitelist — блокирует автоприменение цены/промо/поставки.
  const SAFE_ACTIONS = [
    "open_price_review",
    "open_promo_planner",
    "open_ads_workbench",
    "open_supply_planner",
    "open_data_fix",
    "open_card_review",
    "upload_cost",
    "map_sku",
    "classify_expense",
    "create_task",
    "recheck",
    "dismiss",
    "confirm",
    "open_action_center",
  ];
  const allowed = definition?.allowed_actions_json ?? [];
  const dangerous = allowed.filter((a) => !SAFE_ACTIONS.includes(a));
  if (dangerous.length > 0) {
    blockers.push({
      key: "dangerous_action",
      severity: "blocker",
      message: `Опасное или неизвестное действие: ${dangerous.join(", ")}.`,
      why: "Автоприменение цены/промо/поставки без предпросмотра запрещено. Также нельзя публиковать неизвестные коды действий.",
      fix: "Оставьте только безопасные действия с предпросмотром и подтверждением.",
    });
  }
  if (!firstPrimarySafeAction(allowed)) {
    blockers.push({
      key: "no_allowed_action",
      severity: "blocker",
      message: "Не выбрано ни одно основное безопасное действие.",
      why: "Без действия продавец не поймёт, что делать с проблемой.",
      fix: "Выберите рабочий экран, загрузку данных, поставку, рекламу, цену/промо или проверку карточки.",
    });
  }
  if (priceSafetyMissing(definition, selectedMetrics)) {
    blockers.push({
      key: "price_promo_missing_safety",
      severity: "blocker",
      message:
        "Для правил цены и промо нужны метрики безопасной маржи: cost_price, margin_pct или min_safe_price.",
      why: "Без safety-метрик правило может рекомендовать цену ниже себестоимости.",
      fix: "Добавьте cost_price, margin_pct или min_safe_price в метрики.",
    });
  }
  if (
    definition?.trust_state_default === "test_only" ||
    selectedVersion?.confidence_formula_json === "test_only"
  ) {
    blockers.push({
      key: "test_only_visibility_conflict",
      severity: "blocker",
      message:
        "Правило со статусом «Только тест» нельзя публиковать как видимое продавцу.",
      why: "Test-only правила скрыты от продавца по определению.",
      fix: "Поднимите trust до provisional/estimated/confirmed или оставьте правило в тестовом режиме без публикации.",
    });
  }
  if (backtest && backtest.evaluated_count > 0) {
    const ratio = backtest.matched_count / backtest.evaluated_count;
    if (
      backtest.evaluated_count >= 20 &&
      ratio > 0.5 &&
      !(override && overrideReason.trim())
    ) {
      blockers.push({
        key: "too_many_matches",
        severity: "blocker",
        message:
          "Правило срабатывает слишком широко: больше половины проверенных товаров.",
        why: "Широкий охват создаёт шум и подрывает доверие к платформе.",
        fix: "Ужесточите условие или подтвердите широкий охват с причиной ниже.",
      });
    }
    let highMissing: string | null = null;
    let midMissing: string | null = null;
    for (const [metric, count] of Object.entries(
      backtest.missing_metric_stats,
    )) {
      const r = count / backtest.evaluated_count;
      if (r > 0.5 && !highMissing) highMissing = metric;
      else if (r > 0.3 && r <= 0.5 && !midMissing) midMissing = metric;
    }
    if (highMissing) {
      blockers.push({
        key: "high_missing_metric_rate",
        severity: "blocker",
        message: `Метрика ${highMissing} отсутствует более чем у 50% проверенных товаров.`,
        why: "Слишком высокая доля пропусков — правило нельзя считать надёжным.",
        fix: "Подключите источник метрики или сузьте условие до товаров с данными.",
      });
    } else if (midMissing) {
      blockers.push({
        key: "high_missing_metric_rate",
        severity: "warning",
        message: `Метрика ${midMissing} отсутствует более чем у 30% проверенных товаров.`,
        why: "Заметная доля пропусков снижает надёжность.",
        fix: "Подключите источник метрики или добавьте фильтр по наличию данных.",
      });
    }
  }
  const recheck = selectedVersion?.recheck_rule_json;
  if (
    selectedVersion &&
    (!recheck ||
      (typeof recheck === "object" &&
        !Array.isArray(recheck) &&
        Object.keys(recheck).length === 0))
  ) {
    blockers.push({
      key: "no_recheck_rule",
      severity: "blocker",
      message: "Не задано правило перепроверки.",
      why: "Без перепроверки платформа не знает, когда проблема считается решённой.",
      fix: "На шаге «Повторная проверка» задайте условие завершения.",
    });
  }
  return blockers;
}

function jsonTextsFromPayload(payload: ProblemRuleVersionCreatePayload) {
  return {
    condition_json: prettyJson(payload.condition_json),
    impact_formula_json: prettyJson(payload.impact_formula_json),
    severity_formula_json: prettyJson(payload.severity_formula_json),
    confidence_formula_json: prettyJson(payload.confidence_formula_json),
    recheck_rule_json: prettyJson(payload.recheck_rule_json),
    evidence_template_json: prettyJson(payload.evidence_template_json),
  };
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseLiteral(value: string): string | number | boolean | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  const numeric = Number(trimmed);
  if (!Number.isNaN(numeric) && /^-?\d+(\.\d+)?$/.test(trimmed)) return numeric;
  return trimmed;
}

function slug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function cryptoId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto)
    return crypto.randomUUID();
  return Math.random().toString(36).slice(2);
}
