import type { ReactNode } from "react";

import type {
  MetricCatalogItem,
  ProblemRuleVersionCreatePayload,
} from "@/lib/problem-rules";
import type { JsonValue } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";

export type MatchMode = "and" | "or";
export type ClauseOperator =
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
export type NumericOperator =
  | "none"
  | "+"
  | "-"
  | "*"
  | "/"
  | "max"
  | "min"
  | "percent_change";
export type NumericTransform = "none" | "abs" | "round";
export type OperandKind = "literal" | "metric";
export type MetricBusinessArea =
  | "stock"
  | "sales"
  | "price"
  | "cost"
  | "fees_logistics"
  | "ads"
  | "promo"
  | "returns"
  | "content"
  | "finance"
  | "documents"
  | "sync";

export type ConditionClause = {
  id: string;
  metric: string;
  operator: ClauseOperator;
  value: string;
  valueTo: string;
};

export type NumericBuilderState = {
  metric: string;
  operator: NumericOperator;
  operandKind: OperandKind;
  operandMetric: string;
  operandValue: string;
  transform: NumericTransform;
};

export type RuleBuilderState = {
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

export type AdvancedOverrides = Partial<ProblemRuleVersionCreatePayload>;
export type PublishIssue = {
  key: string;
  severity: "blocker" | "warning";
  message: string;
  /** Почему это важно — короткое пояснение для админа. */
  why?: string;
  /** Как это исправить — короткая инструкция. */
  fix?: string;
};

export const CATEGORY_OPTIONS = [
  "profitability",
  "stock",
  "price",
  "ads_promo",
  "ads",
  "promo",
  "data_quality",
  "system",
];
export const ENTITY_OPTIONS = [
  "product",
  "account",
  "campaign",
  "warehouse",
  "category",
];
export const SEVERITY_OPTIONS = ["critical", "high", "medium", "low"];
export const TRUST_OPTIONS = [
  "confirmed",
  "provisional",
  "estimated",
  "opportunity",
  "blocked",
  "test_only",
];
export const IMPACT_OPTIONS = [
  "confirmed_loss",
  "probable_loss",
  "blocked_cash",
  "lost_sales_risk",
  "opportunity",
  "data_blocker",
  "system_warning",
];
export const ACTION_OPTIONS = [
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

export const CATEGORY_LABELS: Record<string, string> = {
  profitability: "Прибыльность",
  stock: "Остатки",
  price: "Цена",
  ads_promo: "Реклама и промо",
  ads: "Реклама",
  promo: "Промо",
  data_quality: "Качество данных",
  system: "Система",
};

export const METRIC_AREA_ORDER: MetricBusinessArea[] = [
  "stock",
  "sales",
  "price",
  "cost",
  "fees_logistics",
  "ads",
  "promo",
  "returns",
  "content",
  "finance",
  "documents",
  "sync",
];

export const METRIC_AREA_LABELS: Record<MetricBusinessArea, string> = {
  stock: "Остатки",
  sales: "Продажи",
  price: "Цена",
  cost: "Себестоимость",
  fees_logistics: "Комиссии и логистика",
  ads: "Реклама",
  promo: "Промо",
  returns: "Возвраты",
  content: "Контент",
  finance: "Финансы",
  documents: "Документы",
  sync: "Синхронизация",
};

export const ENTITY_LABELS: Record<string, string> = {
  product: "Товар",
  account: "Аккаунт",
  campaign: "Кампания",
  warehouse: "Склад",
  category: "Категория",
};

export const SEVERITY_LABELS: Record<string, string> = {
  critical: "Критично",
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
};

export const TRUST_LABELS: Record<string, string> = {
  confirmed: "Подтверждено",
  provisional: "Предварительно",
  estimated: "Оценка",
  opportunity: "Возможность",
  blocked: "Заблокировано данными",
  test_only: "Только тест",
};

export const IMPACT_LABELS: Record<string, string> = {
  confirmed_loss: "Подтверждённая потеря",
  probable_loss: "Вероятная потеря",
  blocked_cash: "Замороженные деньги",
  lost_sales_risk: "Риск потери продаж",
  opportunity: "Возможность роста",
  data_blocker: "Блокер данных",
  system_warning: "Системное предупреждение",
};

export const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  testing: "Тестируется",
  active: "Активно",
  paused: "На паузе",
  archived: "Архив",
  retired: "Устарело",
};

export const ACTION_LABELS: Record<string, string> = {
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

export const GRAIN_LABELS: Record<string, string> = {
  product_period: "Товар за период",
  product_day: "Товар за день",
  account_day: "Аккаунт за день",
  campaign_day: "Кампания за день",
  warehouse_day: "Склад за день",
};

export const VALUE_TYPE_LABELS: Record<string, string> = {
  money: "Деньги",
  number: "Число",
  percent: "Процент",
  count: "Количество",
  days: "Дни",
  boolean: "Да/нет",
  text: "Текст",
};

export const CLAUSE_OPERATOR_LABELS: Record<string, string> = {
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

export const NUMERIC_OPERATOR_LABELS: Record<string, string> = {
  none: "без операции",
  "+": "плюс",
  "-": "минус",
  "*": "умножить",
  "/": "разделить",
  max: "максимум",
  min: "минимум",
  percent_change: "изменение, %",
};

export const RULE_CREATION_STEPS = [
  "Сценарий",
  "Описание проблемы",
  "Метрики",
  "Условие",
  "Расчёт влияния",
  "Доказательства",
  "Действия",
  "Повторная проверка",
  "Backtest",
  "Seller preview",
  "Publish",
];

export function labelFor(labels: Record<string, string>, code: string): string {
  return labels[code] ?? code;
}

export function optionText(labels: Record<string, string>, code: string): string {
  const label = labelFor(labels, code);
  return label === code ? code : `${label} (${code})`;
}

export function metricBusinessArea(
  metric: MetricCatalogItem,
): MetricBusinessArea {
  const text =
    `${metric.metric_code} ${metric.title ?? ""} ${metric.description ?? ""} ${metric.source_module}`.toLowerCase();
  if (/sync|синхрон|refresh|feed_update|last_updated|stale/.test(text)) return "sync";
  if (/document|акт|invoice|receipt|edo|документ|накладн/.test(text)) return "documents";
  if (/finance|payout|payment|cashflow|balance|финанс|выплат|отчёт|отчет/.test(text)) return "finance";
  if (/stock|остат|warehouse|days_of_stock|supply/.test(text)) return "stock";
  if (/price|цена|margin|min_safe|safe_price/.test(text)) return "price";
  if (/cost|cogs|supplier|себесто/.test(text)) return "cost";
  if (/commission|logistic|storage|fee|tariff|acceptance|комисс|логист/.test(text))
    return "fees_logistics";
  if (/ad_|ads|advert|campaign|cpm|bid|drr|реклам/.test(text)) return "ads";
  if (/promo|discount|скид|промо/.test(text)) return "promo";
  if (/return|refund|возврат/.test(text)) return "returns";
  if (/content|photo|title|description|media|card_quality|rating|контент|карточ/.test(text))
    return "content";
  if (/sale|sales|order|revenue|qty|avg_daily|выруч|продаж/.test(text))
    return "sales";
  return "sales";
}

export function groupMetricsByArea(
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

export function AdminRuleStepper({ activeStep }: { activeStep: number }) {
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

export function StatusBadge({ status }: { status: string }) {
  const variant =
    status === "active"
      ? "default"
      : status === "archived" || status === "retired"
        ? "secondary"
        : "outline";
  return <Badge variant={variant}>{labelFor(STATUS_LABELS, status)}</Badge>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  const variant =
    severity === "critical" || severity === "high"
      ? "destructive"
      : severity === "medium"
        ? "secondary"
        : "outline";
  return <Badge variant={variant}>{labelFor(SEVERITY_LABELS, severity)}</Badge>;
}

export function Field({
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

export function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border px-3 py-2">
      <div className="text-[11px] uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 truncate text-sm font-medium">{value}</div>
    </div>
  );
}

export function TemplatePreview({
  title,
  value,
}: {
  title: string;
  value: string;
}) {
  return (
    <div className="rounded-md border px-3 py-2">
      <div className="text-xs font-medium text-muted-foreground">{title}</div>
      <div className="mt-1 text-sm">{value}</div>
    </div>
  );
}

export function jsonTextsFromPayload(
  payload: ProblemRuleVersionCreatePayload,
) {
  return {
    condition_json: prettyJson(payload.condition_json),
    impact_formula_json: prettyJson(payload.impact_formula_json),
    severity_formula_json: prettyJson(payload.severity_formula_json),
    confidence_formula_json: prettyJson(payload.confidence_formula_json),
    recheck_rule_json: prettyJson(payload.recheck_rule_json),
    evidence_template_json: prettyJson(payload.evidence_template_json),
  };
}

export function prettyJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

export function humanizeCondition(expression: JsonValue): string {
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
